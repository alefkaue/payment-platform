"""Atestação da chave do aparelho (APK Android) -- SEGURANCA.md item 10.

Uma cadeia de verdade só sai do Keystore de um celular, então os testes montam
uma cadeia com a MESMA estrutura (raiz → intermediário → folha com a extensão
KeyDescription) assinada por uma raiz de teste, e trocam as raízes confiáveis.
"""

import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.core import atestacao, dpop
from tests.helpers import QUADROS, SENHA, Pessoa
from tests.test_dpop import Chave

PACOTE = "com.payflow.app"
ASSINATURA = bytes(range(32))

# ---------------------------------------------------------------- DER


def _der(tag: bytes, conteudo: bytes) -> bytes:
    n = len(conteudo)
    tam = bytes([n]) if n < 128 else bytes([0x80 | ((n.bit_length() + 7) // 8)]) + n.to_bytes((n.bit_length() + 7) // 8, "big")
    return tag + tam + conteudo


def seq(*x): return _der(b"\x30", b"".join(x))
def conj(*x): return _der(b"\x31", b"".join(x))
def octeto(b): return _der(b"\x04", b)
def enum(n): return _der(b"\x0a", bytes([n]))
def booleano(v): return _der(b"\x01", b"\xff" if v else b"\x00")


def inteiro(n):
    return _der(b"\x02", n.to_bytes(max(1, (n.bit_length() + 8) // 8), "big", signed=True))


def explicito(tag, interno):
    if tag < 31:
        return _der(bytes([0xA0 | tag]), interno)
    base128 = []
    while True:
        base128.insert(0, tag & 0x7F)
        tag >>= 7
        if not tag:
            break
    marcado = [b | 0x80 for b in base128[:-1]] + [base128[-1]]
    return _der(bytes([0xBF] + marcado), interno)


def descricao(*, nivel=1, desafio=atestacao.DESAFIO, pacote=PACOTE, assinatura=ASSINATURA, travado=True, boot=0):
    app_id = seq(conj(seq(octeto(pacote.encode()), inteiro(1))), conj(octeto(assinatura)))
    sw = seq(explicito(709, octeto(app_id)))
    raiz = seq(octeto(b"\x00" * 32), booleano(travado), enum(boot), octeto(b"\x00" * 32))
    hw = seq(explicito(1, conj(inteiro(2))), explicito(704, raiz))
    return seq(inteiro(300), enum(nivel), inteiro(300), enum(nivel), octeto(desafio), octeto(b""), sw, hw)


# ---------------------------------------------------------------- cadeia


def _nome(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(sujeito, chave_publica, emissor, chave_emissor, *, ext=None, ca=False, inicio=None):
    agora = datetime.now(timezone.utc)
    b = (x509.CertificateBuilder().subject_name(_nome(sujeito)).issuer_name(_nome(emissor))
         .public_key(chave_publica).serial_number(x509.random_serial_number())
         .not_valid_before(inicio or agora - timedelta(days=1)).not_valid_after(agora + timedelta(days=365))
         .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if ext is not None:
        b = b.add_extension(x509.UnrecognizedExtension(atestacao.OID_KEY_DESCRIPTION, ext), critical=False)
    return b.sign(chave_emissor, hashes.SHA256())


class Cadeia:
    def __init__(self):
        self.raiz_chave = ec.generate_private_key(ec.SECP384R1())
        self.raiz = _cert("raiz", self.raiz_chave.public_key(), "raiz", self.raiz_chave, ca=True)
        self.inter_chave = ec.generate_private_key(ec.SECP256R1())
        self.inter = _cert("inter", self.inter_chave.public_key(), "raiz", self.raiz_chave, ca=True)

    def spki_raiz(self):
        import hashlib

        return hashlib.sha256(self.raiz.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).digest()

    def para(self, chave_publica, **kw) -> list[str]:
        folha = _cert("Android Keystore Key", chave_publica, "inter", self.inter_chave, ext=descricao(**kw))
        return [base64.b64encode(c.public_bytes(serialization.Encoding.DER)).decode() for c in (folha, self.inter, self.raiz)]


@pytest.fixture()
def cadeia(monkeypatch):
    c = Cadeia()
    monkeypatch.setattr(atestacao, "raizes_confiaveis", lambda: frozenset({c.spki_raiz()}))
    return c


def _jkt(chave: Chave) -> str:
    return dpop.thumbprint(chave.jwk)


# ---------------------------------------------------------------- verificador


def test_raizes_da_google_carregam():
    assert len(atestacao._RAIZES) == 2


def test_aparelho_integro_com_tee_e_strongbox(cadeia):
    chave = Chave()
    pub = chave.privada.public_key()
    assert atestacao.verificar(cadeia.para(pub), jkt=_jkt(chave)).nivel == "tee"
    assert atestacao.verificar(cadeia.para(pub, nivel=2), jkt=_jkt(chave)).nivel == "strongbox"


@pytest.mark.parametrize("kw, motivo", [
    ({"nivel": 0}, "hardware"),
    ({"travado": False}, "bootloader"),
    ({"boot": 2}, "bootloader"),
])
def test_aparelho_sem_garantia_fica_sem_nivel(cadeia, kw, motivo):
    chave = Chave()
    r = atestacao.verificar(cadeia.para(chave.privada.public_key(), **kw), jkt=_jkt(chave))
    assert r.nivel is None and motivo in r.motivo


def test_chave_atestada_tem_que_ser_a_do_dpop(cadeia):
    # atestação "emprestada" de outro aparelho: a chave dele não assina as provas desta sessão
    outra = Chave()
    with pytest.raises(atestacao.AtestacaoInvalida, match="não é a chave DPoP"):
        atestacao.verificar(cadeia.para(outra.privada.public_key()), jkt=_jkt(Chave()))


def test_raiz_que_nao_e_da_google(monkeypatch):
    chave = Chave()
    falsa = Cadeia()  # sem trocar as raízes confiáveis: vale só a da Google
    with pytest.raises(atestacao.AtestacaoInvalida, match="raiz da Google"):
        atestacao.verificar(falsa.para(chave.privada.public_key()), jkt=_jkt(chave))


def test_folha_assinada_por_outro_intermediario(cadeia):
    chave = Chave()
    certs = cadeia.para(chave.privada.public_key())
    certs[1] = Cadeia().para(chave.privada.public_key())[1]  # intermediário trocado
    with pytest.raises(atestacao.AtestacaoInvalida, match="assinatura inválida"):
        atestacao.verificar(certs, jkt=_jkt(chave))


def test_outro_app_ou_apk_modificado(cadeia, monkeypatch):
    from app.core.config import get_settings

    chave = Chave()
    pub = chave.privada.public_key()
    with pytest.raises(atestacao.AtestacaoInvalida, match="outro app"):
        atestacao.verificar(cadeia.para(pub, pacote="com.golpe.app"), jkt=_jkt(chave))
    with pytest.raises(atestacao.AtestacaoInvalida, match="Desafio"):
        atestacao.verificar(cadeia.para(pub, desafio=b"outro"), jkt=_jkt(chave))
    # com a assinatura do APK configurada, APK reassinado não passa
    monkeypatch.setattr(get_settings(), "atestacao_assinaturas", "AA:" * 31 + "AA")
    with pytest.raises(atestacao.AtestacaoInvalida, match="outro certificado"):
        atestacao.verificar(cadeia.para(pub), jkt=_jkt(chave))
    monkeypatch.setattr(get_settings(), "atestacao_assinaturas", ASSINATURA.hex())
    assert atestacao.verificar(cadeia.para(pub), jkt=_jkt(chave)).nivel == "tee"


def test_certificado_revogado(cadeia, monkeypatch):
    chave = Chave()
    certs = cadeia.para(chave.privada.public_key())
    serie = format(cadeia.inter.serial_number, "x")
    monkeypatch.setattr(atestacao, "series_revogadas", lambda: {serie})
    with pytest.raises(atestacao.AtestacaoInvalida, match="revogado"):
        atestacao.verificar(certs, jkt=_jkt(chave))


def test_lixo_nao_derruba_o_servidor(cadeia):
    for certs in ([], ["não é base64"], [base64.b64encode(b"\x30\x03abc").decode()], ["A" * 12] * 9):
        with pytest.raises(atestacao.AtestacaoInvalida):
            atestacao.verificar(certs, jkt="x")


# ---------------------------------------------------------------- login


def _login(cliente, p: Pessoa, chave: Chave, certs):
    h = {"X-Dispositivo-Id": p.dispositivo}
    e = cliente.post("/auth/login", json={"email": p.email, "senha": SENHA},
                     headers={**h, "DPoP": chave.prova("POST", "/auth/login")}).json()
    corpo = {"mfa_token": e["mfa_token"], "biometria": {"desafio_id": e["desafio"]["desafio_id"], "quadros": QUADROS}}
    if certs is not None:
        corpo["atestacao"] = certs
    return cliente.post("/auth/login/mfa", json=corpo, headers={**h, "DPoP": chave.prova("POST", "/auth/login/mfa")})


def _aparelhos(cliente, tk, p, chave):
    return cliente.get("/seguranca/dispositivos", headers={
        "Authorization": f"Bearer {tk['access_token']}", "X-Dispositivo-Id": p.dispositivo,
        "DPoP": chave.prova("GET", "/seguranca/dispositivos", access_token=tk["access_token"])}).json()


def test_login_registra_o_nivel_do_aparelho(cliente, cadeia):
    p = Pessoa(cliente, "a@ex.com")
    chave = Chave()
    r = _login(cliente, p, chave, cadeia.para(chave.privada.public_key()))
    assert r.status_code == 200, r.text
    assert [d["atestacao"] for d in _aparelhos(cliente, r.json(), p, chave)] == ["tee"]


def test_login_com_atestacao_forjada_e_recusado(cliente, cadeia):
    p = Pessoa(cliente, "a@ex.com")
    chave = Chave()
    r = _login(cliente, p, chave, cadeia.para(Chave().privada.public_key()))
    assert r.status_code == 403


def test_atestacao_exigida_recusa_navegador_e_root(cliente, cadeia, monkeypatch):
    from app.core.config import get_settings

    p = Pessoa(cliente, "a@ex.com")  # cadastra e entra pelo helper, antes de exigir
    monkeypatch.setattr(get_settings(), "atestacao_exigida", True)
    chave = Chave()
    assert _login(cliente, p, chave, None).status_code == 403
    assert _login(cliente, p, chave, cadeia.para(chave.privada.public_key(), travado=False)).status_code == 403
    assert _login(cliente, p, chave, cadeia.para(chave.privada.public_key())).status_code == 200
