"""Atalhos para montar cenários nos testes."""

import random

ADMIN = {"email": "admin@payflow.com.br", "senha": "admin-teste-123"}
QUADROS = ["data:image/png;base64,Zm9v", "data:image/png;base64,YmFy"]


def _dv(base: str, pesos: list[int]) -> str:
    r = sum(int(d) * p for d, p in zip(base, pesos)) % 11
    return "0" if r < 2 else str(11 - r)


def gerar_cpf() -> str:
    base = "".join(str(random.randint(0, 9)) for _ in range(9))
    d1 = _dv(base, list(range(10, 1, -1)))
    d2 = _dv(base + d1, list(range(11, 1, -1)))
    return base + d1 + d2


def gerar_cnpj() -> str:
    base = "".join(str(random.randint(0, 9)) for _ in range(8)) + "0001"
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = _dv(base, p1)
    d2 = _dv(base + d1, [6] + p1)
    return base + d1 + d2


def gerar_chave_nfe(cnpj: str) -> str:
    base = "35" + "2610" + cnpj + "55" + "001" + f"{random.randint(1, 10**9 - 1):09d}" + "1" + f"{random.randint(0, 10**8 - 1):08d}"
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(d) * pesos[i % 8] for i, d in enumerate(reversed(base)))
    r = soma % 11
    return base + str(0 if r < 2 else 11 - r)


def desafio(cliente, token=None) -> str:
    h = {"Authorization": f"Bearer {token}"} if token else {}
    r = cliente.post("/biometria/desafios", headers=h)
    assert r.status_code == 201, r.text
    return r.json()["desafio_id"]


def prova(cliente, token=None) -> dict:
    return {"desafio_id": desafio(cliente, token), "quadros": QUADROS}


class Pessoa:
    def __init__(self, cliente, email: str, *, nome: str | None = None):
        self.cliente = cliente
        self.email = email
        self.cpf = gerar_cpf()
        self.dispositivo = f"aparelho-{email}"
        r = cliente.post(
            "/usuarios",
            json={"nome": nome or email.split("@")[0].title() + " Silva", "email": email, "senha": "senha12345",
                  "cpf": self.cpf, "biometria": prova(cliente)},
            headers={"X-Dispositivo-Id": self.dispositivo},
        )
        assert r.status_code == 201, r.text
        self.conta = r.json()
        self.numero = self.conta["numero"]
        self.token = login(cliente, email, "senha12345", self.dispositivo)

    def h(self, conta: str | None = None, dispositivo: str | None = None) -> dict:
        h = {"Authorization": f"Bearer {self.token}", "X-Dispositivo-Id": dispositivo or self.dispositivo}
        if conta:
            h["X-Conta"] = conta
        return h

    def prova(self) -> dict:
        return prova(self.cliente, self.token)

    def saldo(self, conta: str | None = None) -> str:
        return self.cliente.get("/contas/atual", headers=self.h(conta)).json()["saldo"]

    def transferir(self, destino: dict, valor, *, conta=None, dispositivo=None, **extra):
        return self.cliente.post("/pagamentos/transferir", json={"destino": destino, "valor": str(valor), **extra},
                                 headers=self.h(conta, dispositivo))

    def abrir_empresa(self, **dados) -> dict:
        cnpj = dados.pop("cnpj", None) or gerar_cnpj()
        r = self.cliente.post("/empresas", json={"cnpj": cnpj, "nome_fantasia": "Autopeças Teste", **dados}, headers=self.h())
        assert r.status_code == 201, r.text
        return r.json()


def login(cliente, email, senha, dispositivo=None) -> str:
    h = {"X-Dispositivo-Id": dispositivo} if dispositivo else {}
    r = cliente.post("/auth/login", json={"email": email, "senha": senha}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def admin_h(cliente) -> dict:
    return {"Authorization": f"Bearer {login(cliente, ADMIN['email'], ADMIN['senha'])}"}


def depositar(cliente, numero: str, valor) -> dict:
    r = cliente.post("/admin/depositar", json={"destino": {"numero": numero}, "valor": str(valor)}, headers=admin_h(cliente))
    assert r.status_code == 200, r.text
    return r.json()


def conta_ref(numero: str) -> dict:
    return {"numero": numero}
