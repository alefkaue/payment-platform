"""Troca e recuperação de senha com rosto (SECURITY_AUDIT A-16)."""

from datetime import date

from fastapi import HTTPException

from tests.helpers import QUADROS, SENHA, Pessoa, login_completo

NOVA = "Outra-Chave#Forte42"
NASCIMENTO = "1990-05-17"


def _definir_nascimento(email: str, quando: date | None) -> None:
    from app.db.base import SessionLocal
    from app.db.models import Usuario

    with SessionLocal() as s:
        u = s.query(Usuario).filter_by(email=email).one()
        u.data_nascimento = quando
        s.commit()


def _rosto_reprova(monkeypatch) -> None:
    from app.services import biometria_service

    def reprova(*_a, **_k):
        raise HTTPException(status_code=401, detail="O rosto não confere com o cadastro.")

    monkeypatch.setattr(biometria_service, "verificar", reprova)


def _entra(cliente, email: str, senha: str, dispositivo: str) -> int:
    h = {"X-Dispositivo-Id": dispositivo}
    return cliente.post("/auth/login", json={"email": email, "senha": senha}, headers=h).status_code


# ------------------------------------------------------------------ troca


def test_troca_exige_senha_atual_rosto_e_derruba_as_outras_sessoes(cliente):
    ana = Pessoa(cliente, "ana.troca@ex.com")
    outra = login_completo(cliente, ana.email, SENHA, "notebook-da-ana")
    r = cliente.post("/auth/senha", headers=ana.h(),
                     json={"senha_atual": SENHA, "nova_senha": NOVA, "biometria": ana.prova()})
    assert r.status_code == 200, r.text
    assert r.json()["sessoes_encerradas"] >= 1
    # A sessão do notebook caiu; a atual continua.
    h_outra = {"Authorization": f"Bearer {outra['access_token']}", "X-Dispositivo-Id": "notebook-da-ana"}
    assert cliente.get("/auth/eu", headers=h_outra).status_code == 401
    assert cliente.get("/auth/eu", headers=ana.h()).status_code == 200
    assert _entra(cliente, ana.email, SENHA, ana.dispositivo) == 401
    assert _entra(cliente, ana.email, NOVA, ana.dispositivo) == 200
    acoes = [a["acao"] for a in cliente.get("/seguranca/atividade", headers=ana.h()).json()]
    assert "senha_alterada" in acoes


def test_troca_com_senha_atual_errada_nao_muda_nada(cliente):
    ana = Pessoa(cliente, "ana.errada@ex.com")
    r = cliente.post("/auth/senha", headers=ana.h(),
                     json={"senha_atual": "nao-e-essa-senha", "nova_senha": NOVA, "biometria": ana.prova()})
    assert r.status_code == 401
    assert _entra(cliente, ana.email, SENHA, ana.dispositivo) == 200


def test_troca_sem_rosto_ou_com_rosto_errado_e_recusada(cliente, monkeypatch):
    ana = Pessoa(cliente, "ana.rosto@ex.com")
    r = cliente.post("/auth/senha", headers=ana.h(), json={"senha_atual": SENHA, "nova_senha": NOVA})
    assert r.status_code == 422
    _rosto_reprova(monkeypatch)
    r = cliente.post("/auth/senha", headers=ana.h(),
                     json={"senha_atual": SENHA, "nova_senha": NOVA, "biometria": ana.prova()})
    assert r.status_code == 401
    monkeypatch.undo()
    assert _entra(cliente, ana.email, SENHA, ana.dispositivo) == 200


def test_troca_segue_a_politica_de_senha(cliente):
    ana = Pessoa(cliente, "ana.politica@ex.com")
    for fraca in ("123456789012", SENHA, ana.cpf + "abc"):
        r = cliente.post("/auth/senha", headers=ana.h(),
                         json={"senha_atual": SENHA, "nova_senha": fraca, "biometria": ana.prova()})
        assert r.status_code == 400, fraca


def test_troca_sem_login_nao_responde(cliente):
    r = cliente.post("/auth/senha", json={"senha_atual": SENHA, "nova_senha": NOVA,
                                          "biometria": {"desafio_id": "x" * 20, "quadros": QUADROS}})
    assert r.status_code == 401


# ------------------------------------------------------------ recuperação


def _iniciar(cliente, login: str, nascimento: str, dispositivo: str):
    return cliente.post("/auth/recuperacao", json={"login": login, "data_nascimento": nascimento},
                        headers={"X-Dispositivo-Id": dispositivo})


def _concluir(cliente, etapa: dict, dispositivo: str, senha: str = NOVA):
    return cliente.post("/auth/recuperacao/concluir", headers={"X-Dispositivo-Id": dispositivo}, json={
        "recuperacao_token": etapa["recuperacao_token"], "nova_senha": senha,
        "biometria": {"desafio_id": etapa["desafio"]["desafio_id"], "quadros": QUADROS}})


def test_recuperacao_com_nascimento_e_rosto_troca_a_senha_e_derruba_tudo(cliente):
    ana = Pessoa(cliente, "ana.recupera@ex.com")
    _definir_nascimento(ana.email, date(1990, 5, 17))
    r = _iniciar(cliente, ana.cpf, NASCIMENTO, "celular-novo")
    assert r.status_code == 201, r.text
    assert r.json()["desafio"]["modo"] == "cadastro"  # prova de vida completa
    assert _concluir(cliente, r.json(), "celular-novo").status_code == 204
    assert cliente.get("/auth/eu", headers=ana.h()).status_code == 401  # sessão antiga caiu
    assert _entra(cliente, ana.email, SENHA, ana.dispositivo) == 401
    assert _entra(cliente, ana.email, NOVA, ana.dispositivo) == 200


def test_recuperacao_nao_revela_se_a_conta_existe(cliente):
    ana = Pessoa(cliente, "ana.enum@ex.com")
    _definir_nascimento(ana.email, date(1990, 5, 17))
    respostas = [_iniciar(cliente, ana.email, "2001-01-01", "a1"),         # nascimento errado
                 _iniciar(cliente, "ninguem@ex.com", NASCIMENTO, "a2"),     # conta inexistente
                 _iniciar(cliente, ana.email, NASCIMENTO, "a3")]            # tudo certo
    assert {r.status_code for r in respostas} == {201}
    assert {frozenset(r.json()) for r in respostas} == {frozenset({"recuperacao_token", "expira_em", "desafio"})}
    assert len({len(r.json()["recuperacao_token"]) for r in respostas}) == 1
    # Só a etapa 2 (rosto) diz algo, e a mensagem é a mesma para os dois casos ruins.
    falhas = [_concluir(cliente, respostas[0].json(), "a1"), _concluir(cliente, respostas[1].json(), "a2")]
    assert {r.status_code for r in falhas} == {401}
    assert falhas[0].json()["detail"] == falhas[1].json()["detail"]
    assert _entra(cliente, ana.email, SENHA, ana.dispositivo) == 200


def test_recuperacao_com_rosto_errado_nao_troca_a_senha(cliente, monkeypatch):
    ana = Pessoa(cliente, "ana.outrorosto@ex.com")
    _definir_nascimento(ana.email, date(1990, 5, 17))
    etapa = _iniciar(cliente, ana.email, NASCIMENTO, "celular-ladrao").json()
    _rosto_reprova(monkeypatch)
    r = _concluir(cliente, etapa, "celular-ladrao")
    assert r.status_code == 401
    monkeypatch.undo()
    assert _entra(cliente, ana.email, SENHA, ana.dispositivo) == 200


def test_recuperacao_e_de_uso_unico_e_presa_ao_aparelho(cliente):
    ana = Pessoa(cliente, "ana.unico@ex.com")
    _definir_nascimento(ana.email, date(1990, 5, 17))
    etapa = _iniciar(cliente, ana.email, NASCIMENTO, "celular-1").json()
    assert _concluir(cliente, etapa, "celular-2").status_code == 401  # outro aparelho
    assert _concluir(cliente, etapa, "celular-1").status_code == 204
    # Reenviar o mesmo token (com um desafio novo) não troca de novo.
    etapa["desafio"]["desafio_id"] = _iniciar(cliente, ana.email, NASCIMENTO, "celular-1").json()["desafio"]["desafio_id"]
    assert _concluir(cliente, etapa, "celular-1", senha="Terceira-Chave#99x").status_code == 401
    assert _entra(cliente, ana.email, NOVA, ana.dispositivo) == 200


def test_conta_sem_nascimento_ou_admin_nao_recupera(cliente):
    ana = Pessoa(cliente, "ana.semdata@ex.com")
    _definir_nascimento(ana.email, None)
    etapa = _iniciar(cliente, ana.email, NASCIMENTO, "x1").json()
    assert _concluir(cliente, etapa, "x1").status_code == 401
    etapa = _iniciar(cliente, "admin@payflow.com.br", NASCIMENTO, "x2").json()
    assert _concluir(cliente, etapa, "x2").status_code == 401


def test_recuperacao_tem_limite_por_conta(cliente):
    from app.core.config import get_settings

    ana = Pessoa(cliente, "ana.limite@ex.com")
    maximo = get_settings().recuperacao_max_conta_hora
    codigos = [_iniciar(cliente, ana.email, "2001-01-01", f"ap-{i}").status_code for i in range(maximo + 1)]
    assert codigos[:maximo] == [201] * maximo
    assert codigos[maximo] == 429
    # Inexistente também tem teto (a resposta 429 não diferencia).
    codigos = [_iniciar(cliente, "fantasma@ex.com", NASCIMENTO, f"f-{i}").status_code for i in range(maximo + 1)]
    assert codigos[maximo] == 429
