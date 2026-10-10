"""
Cobranças (Pix com QR dinâmico + boleto), split IBS/CBS e Pix Automático.

É aqui que o split acontece. Uma cobrança pode trazer a nota fiscal da operação
(chave de acesso de 44 dígitos + CBS e IBS destacados nela). No pagamento:
- recebedor no regime REGULAR e nota com imposto -> retém CBS + IBS (vão para a
  conta TRIBUTOS) e o recebedor fica com o líquido;
- recebedor no Simples ou MEI, ou cobrança sem nota -> sem retenção.
O banco NÃO recalcula o imposto: retém o que a nota diz (split_service.split_da_nota).

Checagens da nota: dígito verificador da chave e CNPJ do emitente (posições 7 a
20 da chave) igual ao CNPJ da empresa que está cobrando.

Parcelamento: N cobranças com valor, CBS e IBS proporcionais; a última parcela
absorve os centavos do arredondamento, então a soma das parcelas fecha com o
total (e com o imposto da nota).

Pix Automático: a empresa pede uma autorização (valor máximo + periodicidade); o
pagador aceita; a empresa gera uma cobrança por período e o job
POST /admin/jobs/recorrencias paga as vencidas sozinho. O pagador cancela quando
quiser.

O "pix_copia_e_cola" e a linha digitável são SIMULADOS: emitir Pix/boleto real
exige participar do SPI/DICT (ou um parceiro) e convênio de boleto na Núclea.
"""

from datetime import date
from decimal import ROUND_DOWN, Decimal

from fastapi import HTTPException

from app.core import tempo
from app.core.documentos import (
    chave_nfe_valida,
    cnpj_valido,
    cpf_valido,
    gerar_linha_digitavel,
    gerar_txid,
    somente_digitos,
)
from app.db.models import AuthMetodo, PapelVinculo
from app.deps import exigir_papel, exigir_pj
from app.repositories.exceptions import SaldoInsuficienteError
from app.repositories.repository import Repositorio
from app.services import pix_service, seguranca_service, webhook_service
from app.services.pagamento_service import (
    PODE_MOVIMENTAR,
    AlcadaDiariaExcedida,
    _checar_alcada_diaria,
    _limite_facial,
    chave_idempotencia,
    criar_pendente,
    motivo_aprovacao,
)
from app.services.split_service import sem_split, split_da_nota

_CENTAVO = Decimal("0.01")
SISTEMA = {"id": None, "email": "sistema"}


def pix_copia_e_cola(txid: str) -> str:
    return f"PAYFLOW-SIMULADO.{txid}"


def vai_reter(cobranca: dict) -> bool:
    return cobranca["recebedor"]["regime_apuracao"] == "regular" and (cobranca["cbs"] + cobranca["ibs"]) > 0


def para_resposta(c: dict) -> dict:
    return {**c, "pix_copia_e_cola": pix_copia_e_cola(c["txid"]), "recebedor_nome": c["recebedor"]["nome"],
            "vai_reter_imposto": vai_reter(c)}


def _dividir(total: Decimal, n: int) -> list[Decimal]:
    base = (total / n).quantize(_CENTAVO, rounding=ROUND_DOWN)
    return [base] * (n - 1) + [total - base * (n - 1)]


def _somar_meses(d: date, meses: int) -> date:
    ano, mes = divmod(d.month - 1 + meses, 12)
    ano, mes = d.year + ano, mes + 1
    dias = [31, 29 if ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(ano, mes, min(d.day, dias[mes - 1]))


def _validar_nota(conta: dict, valor: Decimal, nota) -> tuple[str | None, Decimal, Decimal]:
    if nota is None:
        return None, Decimal("0.00"), Decimal("0.00")
    if not chave_nfe_valida(nota.chave):
        raise HTTPException(status_code=400, detail="Chave de acesso da nota fiscal inválida.")
    if nota.chave[6:20] != conta["documento"]:
        raise HTTPException(status_code=400, detail="A nota fiscal foi emitida por outro CNPJ.")
    try:
        split_da_nota(valor, nota.cbs, nota.ibs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return nota.chave, Decimal(nota.cbs), Decimal(nota.ibs)


def criar(repo: Repositorio, *, usuario: dict, conta: dict, dados, ip: str | None) -> list[dict]:
    exigir_pj(conta)
    exigir_papel(conta, *PODE_MOVIMENTAR)
    valor = Decimal(dados.valor)
    chave, cbs, ibs = _validar_nota(conta, valor, dados.nota_fiscal)
    if dados.pagador_documento:
        doc = somente_digitos(dados.pagador_documento)
        if not (cpf_valido(doc) or cnpj_valido(doc)):
            raise HTTPException(status_code=400, detail="Documento do pagador inválido.")
    else:
        doc = None
    n = dados.parcelas
    if n > 1 and dados.vencimento is None:
        raise HTTPException(status_code=400, detail="Cobrança parcelada precisa de data de vencimento.")

    grupo = gerar_txid() if n > 1 else None
    valores, cbss, ibss = _dividir(valor, n), _dividir(cbs, n), _dividir(ibs, n)
    linhas = []
    for i in range(n):
        linhas.append({
            "txid": gerar_txid(), "recebedor_carteira_id": conta["carteira_id"], "valor": valores[i],
            "descricao": dados.descricao if n == 1 else f"{dados.descricao or 'Parcela'} ({i + 1}/{n})",
            "vencimento": _somar_meses(dados.vencimento, i) if dados.vencimento else None,
            "pagador_documento": doc, "nfe_chave": chave, "cbs": cbss[i], "ibs": ibss[i],
            "linha_digitavel": gerar_linha_digitavel(int(valores[i] * 100)), "grupo_parcelamento": grupo,
            "parcela_numero": i + 1, "parcelas_total": n, "criado_por_usuario_id": usuario["id"],
        })
    cobrancas = repo.criar_cobrancas(linhas)
    repo.registrar_log(ator=usuario["email"], acao="cobranca_criada", ip=ip,
                       detalhe={"txids": [c["txid"] for c in cobrancas], "valor": str(valor), "nfe": bool(chave)})
    return cobrancas


def pagar(
    repo: Repositorio,
    *,
    usuario: dict,
    conta: dict,
    dispositivo: dict | None,
    txid: str,
    biometria=None,
    idempotency_key: str | None = None,
    ip: str | None = None,
    mfa_resolvido: bool = False,
    verificacao_previa: dict | None = None,
    pular_alcada: bool = False,
    auth_metodo: AuthMetodo | None = None,
    automatico: bool = False,
) -> dict:
    cob = repo.obter_cobranca(txid=txid)
    if not cob:
        raise HTTPException(status_code=404, detail="Cobrança não encontrada.")
    if cob["status"] != "aberta":
        raise HTTPException(status_code=409, detail=f"Cobrança está '{cob['status']}'.")
    if cob["recebedor"]["carteira_id"] == conta["carteira_id"]:
        raise HTTPException(status_code=400, detail="Não é possível pagar a própria cobrança.")
    if cob["pagador_documento"] and cob["pagador_documento"] != conta["documento"]:
        raise HTTPException(status_code=403, detail="Esta cobrança foi emitida para outro pagador.")
    valor = cob["valor"]

    if not automatico:
        exigir_papel(conta, *PODE_MOVIMENTAR)
        seguranca_service.exigir_dispositivo(dispositivo)
        motivo = None if pular_alcada else motivo_aprovacao(repo, conta, usuario, valor)
        if motivo:
            p = criar_pendente(repo, conta=conta, usuario=usuario, tipo="pagamento_cobranca", valor=valor, ip=ip,
                               payload={"txid": txid}, motivo=motivo)
            return {"pendente": p}

    verificacao = verificacao_previa
    metodo = auth_metodo or (AuthMetodo.AUTOMATICO if automatico else AuthMetodo.SELFIE if verificacao else AuthMetodo.SENHA)
    if not automatico and not mfa_resolvido and verificacao is None and valor > _limite_facial():
        verificacao = seguranca_service.verificar_rosto(repo, usuario=usuario, prova=biometria, ip=ip, tipo="pagamento_cobranca")
        metodo = auth_metodo or AuthMetodo.SELFIE

    split = split_da_nota(valor, cob["cbs"], cob["ibs"]) if vai_reter(cob) else sem_split(valor)
    checar = None if automatico else seguranca_service.checador_de_limites(
        valor=valor, titular_tipo=conta["titular_tipo"], dispositivo=dispositivo)
    if not automatico and not pular_alcada:
        checar = _checar_alcada_diaria(conta, usuario, valor, checar)
    try:
        t = repo.executar_movimento(
            origem_id=conta["carteira_id"], destino_id=cob["recebedor"]["carteira_id"], split=split, tipo="cobranca",
            auth_metodo=metodo, autor_usuario_id=usuario["id"], dispositivo_id=dispositivo["id"] if dispositivo else None,
            descricao=cob["descricao"] or f"Cobrança {txid}", verificacao_facial=verificacao,
            idempotency_key=chave_idempotencia(conta, idempotency_key), checar=checar, cobranca_id=cob["id"],
        )
    except SaldoInsuficienteError:
        raise HTTPException(status_code=400, detail="Saldo insuficiente.")
    except AlcadaDiariaExcedida:
        p = criar_pendente(repo, conta=conta, usuario=usuario, tipo="pagamento_cobranca", valor=valor, ip=ip,
                           payload={"txid": txid}, motivo="alcada_diaria")
        return {"pendente": p}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    repo.registrar_log(ator=usuario["email"], acao="cobranca_paga", ip=ip, detalhe={
        "txid": txid, "transacao_id": t["id"], "cbs": str(t["cbs"]), "ibs": str(t["ibs"]), "auth": metodo.value,
    })
    webhook_service.emitir(repo, empresa_id=cob["recebedor"]["empresa_id"], evento="cobranca.paga", payload={
        "txid": txid, "transacao_id": t["id"], "valor": t["valor_bruto"], "liquido": t["liquido"],
        "cbs": t["cbs"], "ibs": t["ibs"], "nfe_chave": cob["nfe_chave"],
    })
    return {"transacao": t}


def cancelar(repo: Repositorio, *, usuario: dict, conta: dict, txid: str, ip: str | None) -> None:
    exigir_pj(conta)
    exigir_papel(conta, *PODE_MOVIMENTAR)
    cob = repo.obter_cobranca(txid=txid)
    if not cob or cob["recebedor"]["carteira_id"] != conta["carteira_id"]:
        raise HTTPException(status_code=404, detail="Cobrança não encontrada.")
    if not repo.cancelar_cobranca(cob["id"]):
        raise HTTPException(status_code=409, detail="Só cobranças abertas podem ser canceladas.")
    repo.registrar_log(ator=usuario["email"], acao="cobranca_cancelada", ip=ip, detalhe={"txid": txid})


def estornar(repo: Repositorio, *, usuario: dict, conta: dict, txid: str, ip: str | None) -> dict:
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    cob = repo.obter_cobranca(txid=txid)
    if not cob or cob["recebedor"]["carteira_id"] != conta["carteira_id"]:
        raise HTTPException(status_code=404, detail="Cobrança não encontrada.")
    if cob["status"] != "paga":
        raise HTTPException(status_code=409, detail="Só cobranças pagas podem ser estornadas.")
    try:
        t = repo.estornar_cobranca(cobranca_id=cob["id"], autor_usuario_id=usuario["id"])
    except SaldoInsuficienteError:
        raise HTTPException(status_code=400, detail="Saldo insuficiente para devolver o valor ao pagador.")
    repo.registrar_log(ator=usuario["email"], acao="cobranca_estornada", ip=ip, detalhe={"txid": txid, "transacao_id": t["id"]})
    webhook_service.emitir(repo, empresa_id=conta["empresa_id"], evento="cobranca.estornada",
                           payload={"txid": txid, "transacao_id": t["id"], "valor": t["valor_bruto"]})
    return t


# =============================================================================
# Pix Automático
# =============================================================================


def _periodo(d: date, periodicidade: str) -> tuple:
    if periodicidade == "semanal":
        return tuple(d.isocalendar()[:2])
    if periodicidade == "mensal":
        return (d.year, d.month)
    return (d.year,)


def criar_autorizacao(repo: Repositorio, *, usuario: dict, conta: dict, dados, ip: str | None) -> dict:
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN, PapelVinculo.OPERADOR)
    pagador = pix_service.resolver_destino(repo, dados.pagador)
    if pagador["carteira_id"] == conta["carteira_id"]:
        raise HTTPException(status_code=400, detail="A empresa não pode autorizar a si mesma.")
    a = repo.criar_autorizacao(
        recebedor_carteira_id=conta["carteira_id"], pagador_carteira_id=pagador["carteira_id"],
        descricao=dados.descricao, valor_maximo=dados.valor_maximo, periodicidade=dados.periodicidade,
    )
    repo.registrar_log(ator=usuario["email"], acao="pix_automatico_solicitado", ip=ip, detalhe={"autorizacao_id": a["id"]})
    return a


def responder_autorizacao(repo: Repositorio, *, usuario: dict, conta: dict, dispositivo: dict | None, autorizacao_id: int,
                          aceitar: bool, ip: str | None) -> dict:
    a = repo.obter_autorizacao(autorizacao_id)
    if not a or a["pagador"]["carteira_id"] != conta["carteira_id"]:
        raise HTTPException(status_code=404, detail="Autorização não encontrada.")
    if a["status"] != "pendente":
        raise HTTPException(status_code=409, detail=f"Autorização está '{a['status']}'.")
    exigir_papel(conta, PapelVinculo.ADMIN)
    seguranca_service.exigir_dispositivo(dispositivo)
    campos = {"status": "ativa", "aceita_em": tempo.agora()} if aceitar else {"status": "recusada"}
    a = repo.atualizar_autorizacao(autorizacao_id, **campos)
    repo.registrar_log(ator=usuario["email"], acao="pix_automatico_" + ("aceito" if aceitar else "recusado"), ip=ip,
                       detalhe={"autorizacao_id": autorizacao_id})
    return a


def cancelar_autorizacao(repo: Repositorio, *, usuario: dict, conta: dict, autorizacao_id: int, ip: str | None) -> dict:
    a = repo.obter_autorizacao(autorizacao_id)
    lado = None
    if a and a["pagador"]["carteira_id"] == conta["carteira_id"]:
        lado = "pagador"
    elif a and a["recebedor"]["carteira_id"] == conta["carteira_id"]:
        lado = "recebedor"
    if lado is None:
        raise HTTPException(status_code=404, detail="Autorização não encontrada.")
    exigir_papel(conta, PapelVinculo.ADMIN)
    if a["status"] in ("cancelada", "recusada"):
        return a
    a = repo.atualizar_autorizacao(autorizacao_id, status="cancelada", cancelada_em=tempo.agora())
    for c in repo.cobrancas_da_autorizacao(autorizacao_id):
        if c["status"] == "aberta":
            repo.cancelar_cobranca(c["id"])
    repo.registrar_log(ator=usuario["email"], acao="pix_automatico_cancelado", ip=ip,
                       detalhe={"autorizacao_id": autorizacao_id, "por": lado})
    return a


def cobrar_recorrente(repo: Repositorio, *, usuario: dict, conta: dict, autorizacao_id: int, dados, ip: str | None) -> dict:
    exigir_pj(conta)
    exigir_papel(conta, *PODE_MOVIMENTAR)
    a = repo.obter_autorizacao(autorizacao_id)
    if not a or a["recebedor"]["carteira_id"] != conta["carteira_id"]:
        raise HTTPException(status_code=404, detail="Autorização não encontrada.")
    if a["status"] != "ativa":
        raise HTTPException(status_code=409, detail="A autorização não está ativa.")
    valor = Decimal(dados.valor)
    if valor > a["valor_maximo"]:
        raise HTTPException(status_code=400, detail="Valor acima do máximo autorizado pelo pagador.")
    periodo = _periodo(dados.vencimento, a["periodicidade"])
    if any(c["vencimento"] and _periodo(c["vencimento"], a["periodicidade"]) == periodo
           for c in repo.cobrancas_da_autorizacao(autorizacao_id)):
        raise HTTPException(status_code=409, detail="Já existe cobrança desta autorização neste período.")
    chave, cbs, ibs = _validar_nota(conta, valor, dados.nota_fiscal)
    [cob] = repo.criar_cobrancas([{
        "txid": gerar_txid(), "recebedor_carteira_id": conta["carteira_id"], "valor": valor,
        "descricao": dados.descricao or a["descricao"], "vencimento": dados.vencimento, "nfe_chave": chave,
        "cbs": cbs, "ibs": ibs, "linha_digitavel": gerar_linha_digitavel(int(valor * 100)),
        "autorizacao_id": autorizacao_id, "criado_por_usuario_id": usuario["id"],
    }])
    repo.registrar_log(ator=usuario["email"], acao="pix_automatico_cobranca", ip=ip,
                       detalhe={"autorizacao_id": autorizacao_id, "txid": cob["txid"]})
    return cob


def processar_recorrencias(repo: Repositorio) -> dict:
    pagas, falhas = 0, []
    for cob in repo.cobrancas_recorrentes_vencidas(tempo.hoje_brt()):
        a = repo.obter_autorizacao(cob["autorizacao_id"])
        pagador = repo.obter_conta(a["pagador"]["carteira_id"])
        try:
            pagar(repo, usuario=SISTEMA, conta={**pagador, "vinculo": None}, dispositivo=None, txid=cob["txid"],
                  idempotency_key=f"recorrencia-{cob['id']}", automatico=True)
            pagas += 1
        except HTTPException as e:
            falhas.append({"txid": cob["txid"], "erro": str(e.detail)})
    return {"pagas": pagas, "falhas": falhas}
