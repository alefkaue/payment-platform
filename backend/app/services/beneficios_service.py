"""
Benefícios da conta PF: Loja PayFlow, Viagens e pontos — o diferencial do PF
(o do PJ é o split).

- Comprar na Loja ou uma passagem EM REAIS: o parceiro (PJ, regime regular)
  emite a nota na hora e a compra vira o pagamento de uma cobrança com essa nota.
  Assim vale tudo que vale para qualquer pagamento: split da CBS/IBS da nota,
  limites, aparelho, verificação facial acima de R$ 500. Cada R$ 1 pago rende
  1 ponto.
- RESGATE de passagem com pontos: debita `milhas` pontos do cliente e o PayFlow
  paga o parceiro a partir do CAIXA (a venda continua com nota e split). Não
  movimenta o saldo em reais do cliente.
- Só contas PF compram (PJ recebe as vendas com split).

Catálogo: produtos e voos ficam no banco e são criados no boot a partir de
CATALOGO_* abaixo (mesmos itens do modo demonstração do app).
"""

from decimal import ROUND_DOWN, Decimal

from fastapi import HTTPException

from app.core import tempo
from app.core.documentos import cnpj_com_dv, gerar_chave_nfe, gerar_linha_digitavel, gerar_txid
from app.db.models import AuthMetodo
from app.repositories.repository import Repositorio
from app.services import cobranca_service, seguranca_service
from app.services.split_service import estimar, split_da_nota

LOJISTAS = {
    "techponto": ("TechPonto", "Comércio · Eletrônicos"),
    "modaviva": ("ModaViva", "Comércio · Moda"),
    "mercadonorte": ("Mercado Norte", "Comércio · Varejo"),
    "padaria": ("Padaria Aurora", "Comércio · Alimentos"),
    "farmacia": ("Farmácia Bem", "Comércio · Saúde"),
    "livraria": ("Livraria Sol", "Comércio · Livros"),
    "viagens": ("Astro Viagens", "Turismo · Agência"),
}

CATALOGO_PRODUTOS = [
    ("Fones Bluetooth Pulse", "Cancelamento de ruído, 30h de bateria.", "349.90", "Eletrônicos", "🎧", "techponto"),
    ("Tênis Urban Run", "Leve, respirável, para corrida e dia a dia.", "299.00", "Moda", "👟", "modaviva"),
    ("Cafeteira Italiana", "Café cremoso em casa, 6 xícaras.", "159.90", "Casa", "☕", "mercadonorte"),
    ("Cesta de Pães Artesanais", "Seleção fresca da padaria, entrega no dia.", "48.50", "Alimentos", "🥐", "padaria"),
    ("Kit Skincare Vitamina C", "Limpeza, sérum e hidratante.", "129.90", "Saúde", "🧴", "farmacia"),
    ("Smartwatch Fit 2", "Monitor cardíaco, GPS e notificações.", "629.00", "Eletrônicos", "⌚", "techponto"),
    ('Box de Livros "Clássicos"', "5 obras essenciais em capa dura.", "189.90", "Livros", "📚", "livraria"),
    ("Jaqueta Corta-vento", "Impermeável, dobrável, unissex.", "219.90", "Moda", "🧥", "modaviva"),
]

CATALOGO_VOOS = [
    ("GRU", "São Paulo", "GIG", "Rio de Janeiro", "Azul Linhas", "08:15", "09:20", "1h05", True, "319.90", 9000),
    ("GRU", "São Paulo", "GIG", "Rio de Janeiro", "LATAM", "13:40", "14:50", "1h10", True, "289.00", 8000),
    ("GRU", "São Paulo", "SSA", "Salvador", "GOL", "06:00", "08:55", "2h55", True, "612.40", 17000),
    ("GRU", "São Paulo", "REC", "Recife", "Azul Linhas", "22:10", "01:30", "3h20", True, "748.00", 21000),
    ("CGH", "São Paulo", "BSB", "Brasília", "LATAM", "09:30", "11:10", "1h40", True, "455.50", 13000),
    ("GRU", "São Paulo", "POA", "Porto Alegre", "GOL", "17:45", "19:25", "1h40", False, "398.90", 11000),
]


def garantir_catalogo(repo: Repositorio) -> None:
    carteiras = {}
    for i, (chave, (nome, setor)) in enumerate(LOJISTAS.items(), start=1):
        cnpj = cnpj_com_dv(f"{90000000 + i:08d}0001")
        carteiras[chave] = repo.garantir_lojista(cnpj=cnpj, nome=nome, setor=setor)
    if not repo.catalogo_vazio():
        return
    produtos = [
        {"nome": n, "descricao": d, "preco": Decimal(p), "categoria": c, "emoji": e, "lojista_carteira_id": carteiras[l]}
        for n, d, p, c, e, l in CATALOGO_PRODUTOS
    ]
    voos = [
        {"origem": o, "origem_cidade": oc, "destino": d, "destino_cidade": dc, "companhia": cia, "saida": s,
         "chegada": ch, "duracao": du, "direto": di, "preco": Decimal(p), "milhas": m,
         "parceiro_carteira_id": carteiras["viagens"]}
        for o, oc, d, dc, cia, s, ch, du, di, p, m in CATALOGO_VOOS
    ]
    repo.criar_catalogo(produtos, voos)


def _exigir_pf(conta: dict) -> None:
    if conta["titular_tipo"] != "PF":
        raise HTTPException(status_code=403, detail="Loja e Viagens são benefícios das contas Pessoa Física.")


def _nota_da_venda(repo: Repositorio, parceiro_carteira_id: int, valor: Decimal) -> tuple[str, Decimal, Decimal]:
    """O parceiro emite a nota da venda: CBS/IBS do ano corrente (regime padrão)."""
    parceiro = repo.obter_conta(parceiro_carteira_id)
    e = estimar(valor)
    return gerar_chave_nfe(parceiro["documento"]), e["cbs"], e["ibs"]


def _vender(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, parceiro_carteira_id: int,
            valor: Decimal, descricao: str, motivo_pontos: str, biometria, ip: str | None) -> dict:
    _exigir_pf(conta)
    chave, cbs, ibs = _nota_da_venda(repo, parceiro_carteira_id, valor)
    [cob] = repo.criar_cobrancas([{
        "txid": gerar_txid(), "recebedor_carteira_id": parceiro_carteira_id, "valor": valor,
        "descricao": descricao, "vencimento": tempo.hoje_brt(), "pagador_documento": conta["documento"],
        "nfe_chave": chave, "cbs": cbs, "ibs": ibs, "linha_digitavel": gerar_linha_digitavel(int(valor * 100)),
    }])
    try:
        r = cobranca_service.pagar(repo, usuario=usuario, conta=conta, dispositivo=dispositivo, txid=cob["txid"],
                                   biometria=biometria, ip=ip)
    except HTTPException:
        repo.cancelar_cobranca(cob["id"])
        raise
    t = r["transacao"]
    pontos = int(Decimal(valor).to_integral_value(rounding=ROUND_DOWN))
    saldo = repo.mover_pontos(usuario_id=usuario["id"], delta=pontos, motivo=motivo_pontos, descricao=descricao,
                              transacao_id=t["id"])
    return {"transacao": t, "pontos_ganhos": pontos, "saldo_pontos": saldo}


def comprar_produto(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, produto_id: int,
                    biometria, ip: str | None) -> dict:
    p = repo.obter_produto(produto_id)
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return _vender(repo, usuario=usuario, conta=conta, dispositivo=dispositivo,
                   parceiro_carteira_id=p["merchant_carteira_id"], valor=p["preco"],
                   descricao=f"{p['merchant_nome']} · {p['nome']}", motivo_pontos="compra_loja",
                   biometria=biometria, ip=ip)


def comprar_voo(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, voo_id: int,
                biometria, ip: str | None) -> dict:
    v = repo.obter_voo(voo_id)
    if not v:
        raise HTTPException(status_code=404, detail="Voo não encontrado.")
    return _vender(repo, usuario=usuario, conta=conta, dispositivo=dispositivo,
                   parceiro_carteira_id=v["merchant_carteira_id"], valor=v["preco"],
                   descricao=f"Voo {v['origem']} → {v['destino']} · {v['companhia']}", motivo_pontos="compra_voo",
                   biometria=biometria, ip=ip)


def resgatar_voo(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, voo_id: int,
                 ip: str | None) -> dict:
    """Passagem com pontos: o cliente não paga em reais; o PayFlow paga o parceiro."""
    _exigir_pf(conta)
    seguranca_service.exigir_dispositivo(dispositivo)
    v = repo.obter_voo(voo_id)
    if not v:
        raise HTTPException(status_code=404, detail="Voo não encontrado.")
    descricao = f"Resgate · Voo {v['origem']} → {v['destino']} · {v['companhia']}"
    try:
        saldo = repo.mover_pontos(usuario_id=usuario["id"], delta=-v["milhas"], motivo="resgate_voo",
                                  descricao=descricao)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Pontos insuficientes: este voo custa {v['milhas']:,} pontos.".replace(",", "."))
    try:
        chave, cbs, ibs = _nota_da_venda(repo, v["merchant_carteira_id"], v["preco"])
        caixa = repo.carteira_sistema("CAIXA")
        t = repo.executar_movimento(
            origem_id=caixa["carteira_id"], destino_id=v["merchant_carteira_id"],
            split=split_da_nota(v["preco"], cbs, ibs), tipo="resgate_pontos", auth_metodo=AuthMetodo.SISTEMA,
            autor_usuario_id=usuario["id"], descricao=descricao, permitir_saldo_negativo=True,
        )
    except Exception:
        repo.mover_pontos(usuario_id=usuario["id"], delta=v["milhas"], motivo="estorno_resgate",
                          descricao=f"Estorno · {descricao}")
        raise
    repo.registrar_log(ator=usuario["email"], acao="resgate_voo", ip=ip,
                       detalhe={"voo_id": voo_id, "pontos": v["milhas"], "transacao_id": t["id"], "nfe": chave})
    return {
        "localizador": gerar_txid()[:6].upper(),
        "voo": v,
        "pontos_usados": v["milhas"],
        "saldo_pontos": saldo,
    }
