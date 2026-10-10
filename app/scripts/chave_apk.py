"""
Gera a chave de assinatura do APK release (uma vez só; SEGURANCA.md item 10).

    backend/.venv/Scripts/python.exe app/scripts/chave_apk.py

Cria `astro-release.p12` (PKCS12, que o Gradle/JDK 21 aceita como keystore) FORA do
repositório e imprime o que vai em cada secret do GitHub. Perder esta chave = não dá
para atualizar o app por cima; vazar = alguém publica um APK "nosso". Guarde o .p12 e a
senha num gerenciador de senhas e apague a cópia local depois de criar os secrets.

No PKCS12 a senha da chave é a mesma do arquivo (o Java exige isso).
"""

import base64
import hashlib
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

sys.stdout.reconfigure(encoding="utf-8")

ALIAS = "astro"
destino = Path.home() / "astro-release.p12"
if destino.exists():
    raise SystemExit(f"{destino} já existe: não sobrescrevo uma chave de assinatura.")

senha = secrets.token_urlsafe(24)
chave = rsa.generate_private_key(public_exponent=65537, key_size=3072)
nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Astro"), x509.NameAttribute(NameOID.COUNTRY_NAME, "BR")])
agora = datetime.now(timezone.utc)
cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(agora)
        .not_valid_after(agora + timedelta(days=365 * 30))  # a Play pede validade depois de 2033
        .sign(chave, hashes.SHA256()))

dados = pkcs12.serialize_key_and_certificates(ALIAS.encode(), chave, cert, None,
                                              serialization.BestAvailableEncryption(senha.encode()))
destino.write_bytes(dados)

print(f"Keystore: {destino}\n")
print("Secrets do repositório (Settings > Secrets and variables > Actions > Secrets):")
print(f"  ANDROID_KEYSTORE_SENHA = {senha}")
print(f"  ANDROID_KEY_SENHA      = {senha}")
print(f"  ANDROID_KEY_ALIAS      = {ALIAS}")
print("  ANDROID_KEYSTORE_B64   = (conteúdo abaixo, uma linha)\n")
print(base64.b64encode(dados).decode())
print(f"\nATESTACAO_ASSINATURAS (backend) = {hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()}")
