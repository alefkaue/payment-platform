"""
Gera ENDPOINTS.md (raiz do repositório) a partir das rotas REAIS da API.

    cd backend && .venv/Scripts/python.exe scripts/inventario_endpoints.py

A coluna "Autenticação" vem das dependências de cada rota (usuario_atual / admin_atual);
"Conta" indica que a rota opera a conta escolhida no header X-Conta (conferida contra os
vínculos da pessoa em deps.conta_atual). As regras de papel ficam nos serviços, então
vêm do dicionário REGRAS abaixo -- mantenha junto quando mudar um serviço.
"""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("JWT_SECRET", "inventario-inventario-inventario-32")
os.environ.setdefault("EMBEDDING_KEY", "OTglUQywNhpctpSAKAF71Rz5qH8BLx5plpEZLSij0kk=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.core.rotas import todas_as_rotas  # noqa: E402
from app.main import app  # noqa: E402

PJ_ADMIN = "PJ: admin"
MOVIMENTA = "PJ: admin/aprovador/operador; alçada, alçada diária e assinatura conjunta → pendente"
REGRAS = {
    ("POST", "/auth/login"): "Senha (1º fator) + DPoP; limites por conta+IP, por conta e por IP",
    ("POST", "/auth/login/mfa"): "Rosto com prova de vida sorteada (2º fator); mesmo aparelho e chave DPoP; atestação opcional (APK)",
    ("POST", "/auth/refresh"): "Refresh preso à chave DPoP e ao aparelho; rotação; limite por IP",
    ("POST", "/auth/logout"): "Revoga a sessão inteira (família de refresh)",
    ("POST", "/auth/senha"): "Senha atual + rosto; política de senha; encerra as outras sessões",
    ("POST", "/auth/recuperacao"): "E-mail/CPF + nascimento; resposta igual exista a conta ou não; limite por IP e por conta",
    ("POST", "/auth/recuperacao/concluir"): "Rosto com prova de vida completa, mesmo aparelho e chave; uso único; derruba todas as sessões",
    ("POST", "/usuarios"): "Cadastro com KYC (rosto + documento); limite por IP; resposta neutra",
    ("POST", "/biometria/desafios"): "Desafio de prova de vida (uso único, 120 s)",
    ("POST", "/empresas"): "Pessoa com KYC; CNPJ conferido (BrasilAPI) e CPF no quadro de sócios",
    ("POST", "/empresas/atual/vinculos"): PJ_ADMIN + "; dar poder exige rosto; Grande: 4 olhos",
    ("PATCH", "/empresas/atual/vinculos/{vinculo_id}"): PJ_ADMIN + "; aumentar poder/alçada exige rosto; Grande: 4 olhos",
    ("POST", "/empresas/atual/vinculos/{vinculo_id}/suspender"): PJ_ADMIN + "; nunca o último admin",
    ("POST", "/empresas/atual/vinculos/{vinculo_id}/reativar"): PJ_ADMIN + "; rosto; Grande: 4 olhos",
    ("DELETE", "/empresas/atual/vinculos/{vinculo_id}"): PJ_ADMIN + "; nunca o último admin",
    ("GET", "/empresas/atual/pendentes"): "PJ: exceto consulta; expira as vencidas antes de listar",
    ("POST", "/convites/{vinculo_id}/aceitar"): "Só a dona do CPF convidado, com KYC e rosto",
    ("POST", "/empresas/atual/funcionarios"): PJ_ADMIN,
    ("DELETE", "/empresas/atual/funcionarios/{funcionario_id}"): PJ_ADMIN,
    ("POST", "/empresas/atual/folha/pagar"): MOVIMENTA + "; destino resolvido pelo CPF no servidor",
    ("POST", "/pagamentos/transferir"): MOVIMENTA + "; rosto acima de R$ 500; limites e aparelho no lock",
    ("POST", "/pagamentos/lote"): MOVIMENTA + " (por item); até 100 itens",
    ("POST", "/pagamentos/pendentes/{operacao_id}/decidir"): "Aprovar: admin/aprovador ≠ quem lançou, dentro da alçada, rosto; cancelar: quem lançou",
    ("POST", "/pagamentos/transacoes/{transacao_id}/contestar"): "Só transação da conta em uso (MED)",
    ("POST", "/pagamentos/depositar-demo"): "Só com DEPOSITO_DEMO=1 (recusado em produção)",
    ("POST", "/cobrancas"): "PJ: admin/aprovador/operador",
    ("GET", "/cobrancas/{txid}"): "Quem tem o txid; documento do pagador mascarado para terceiros",
    ("POST", "/cobrancas/{txid}/pagar"): MOVIMENTA + "; pagador indicado na cobrança",
    ("POST", "/cobrancas/{txid}/cancelar"): "PJ que emitiu",
    ("POST", "/cobrancas/{txid}/estornar"): "PJ que emitiu: admin",
    ("PUT", "/seguranca/limites"): "PJ: admin; aumento só vale após carência de 24 h",
    ("POST", "/seguranca/dispositivos/{dispositivo_id}/desbloquear"): "Rosto",
    ("GET", "/empresas/atual/auditoria"): "PJ: admin/aprovador",
    ("POST", "/empresas/atual/webhooks"): PJ_ADMIN + "; URL https pública (anti-SSRF)",
    ("GET", "/pix/consultar/{chave}"): "Nome mascarado; 60 consultas/hora por pessoa",
    ("POST", "/admin/depositar"): "Admin; IP na lista ADMIN_IPS_PERMITIDOS (sem lista: desligado em produção)",
}


def _deps(dependant, out):
    for d in dependant.dependencies:
        out.add(getattr(d.call, "__name__", ""))
        _deps(d, out)


def main():
    linhas = []
    for r in todas_as_rotas(app):
        nomes: set[str] = set()
        _deps(r.dependant, nomes)
        auth = "admin + IP" if "admin_atual" in nomes else ("login + DPoP" if "usuario_atual" in nomes else "pública")
        conta = "X-Conta" if "conta_atual" in nomes else ""
        for m in sorted(r.methods):
            linhas.append((r.path, m, auth, conta, REGRAS.get((m, r.path), "")))
    corpo = "\n".join(f"| `{m}` | `{p}` | {a} | {c} | {g} |" for p, m, a, c, g in linhas)
    texto = f"""# Astro — inventário de endpoints

> Gerado por `backend/scripts/inventario_endpoints.py` a partir das rotas reais ({len(linhas)} rotas).
> Não edite à mão: rode o script de novo quando a API mudar.

- **pública**: sem login (as de autenticação têm limite por IP e/ou DPoP).
- **login + DPoP**: access token (Bearer) + prova DPoP da chave do aparelho + sessão ativa
  (encerrada/expirada cai na hora). Sem login, todas respondem 401/403
  (`tests/test_autorizacao_objetos.py::test_sem_login_nada_protegido_responde`).
- **admin + IP**: além disso, papel admin da plataforma e IP em `ADMIN_IPS_PERMITIDOS`.
- **X-Conta**: opera a conta escolhida; o servidor confere o vínculo ATIVO da pessoa com
  aquela empresa (`deps.conta_atual`). Recurso de outra conta responde 404
  (`tests/test_autorizacao_objetos.py::test_ninguem_usa_recurso_de_outro`).
- Loja/Viagens/Pontos: desligados por padrão (`BENEFICIOS_HABILITADOS=0` → 404).

| Método | Caminho | Autenticação | Conta | Regra adicional no serviço |
|---|---|---|---|---|
{corpo}
"""
    destino = RAIZ.parent / "ENDPOINTS.md"
    destino.write_text(texto, encoding="utf-8")
    print(f"{destino} ({len(linhas)} rotas)")


if __name__ == "__main__":
    main()
