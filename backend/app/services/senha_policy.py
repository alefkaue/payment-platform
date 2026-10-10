"""
Política de senha (NIST SP 800-63B / OWASP ASVS): comprimento mínimo, lista de
senhas comuns e dados da própria pessoa -- SEM regras de composição ("precisa de
1 maiúscula e 1 símbolo"), que pioram a senha média sem ganho real.

- mínimo SENHA_MIN (padrão 10), máximo 128;
- recusa senhas da lista das mais usadas no Brasil/mundo (e variações com
  dígitos no fim);
- recusa senha que contenha o CPF, a parte local do e-mail ou o nome;
- recusa repetição/sequência óbvia (aaaaaaaaaa, 1234567890, qwertyuiop).

A senha é só UM fator: o login sempre exige também o rosto (prova de vida).
"""

import re
import unicodedata

from fastapi import HTTPException

from app.core.config import get_settings

_COMUNS = {
    "123456", "1234567", "12345678", "123456789", "1234567890", "12345678910", "senha", "senha123", "senha1234",
    "senha12345", "senha123456", "password", "password1", "passw0rd", "qwerty", "qwerty123", "abc123", "abcdef",
    "111111", "000000", "123123", "654321", "iloveyou", "admin", "admin123", "administrador", "brasil", "brasil123",
    "flamengo", "corinthians", "palmeiras", "saopaulo", "gremio", "vasco", "santos", "cruzeiro", "botafogo",
    "fluminense", "internacional", "atletico", "mudar123", "mudar1234", "trocar123", "teste", "teste123",
    "teste1234", "102030", "10203040", "1020304050", "112233", "121212", "131313", "159753", "147258", "147258369",
    "123321", "asdfgh", "asdfghjkl", "qwertyuiop", "zxcvbnm", "amor", "amor123", "jesus", "jesus123", "deus",
    "deusefiel", "familia", "felicidade", "minhasenha", "mudarsenha", "banco", "banco123", "astro", "astro123",
    "payflow", "payflow123", "pix", "pix123", "dinheiro", "dragon", "monkey", "letmein", "welcome", "football",
    "princesa", "gabriel", "lucas", "mateus", "beatriz", "juliana", "fernanda", "rafael", "bruno", "camila",
}
_SEQUENCIAS = ("0123456789", "1234567890", "abcdefghijklmnopqrstuvwxyz", "qwertyuiop", "asdfghjkl", "zxcvbnm")


def _norm(s: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return sem_acento.lower()


def validar(senha: str, *, email: str = "", cpf: str = "", nome: str = "") -> None:
    minimo = get_settings().senha_min
    if len(senha) < minimo:
        raise HTTPException(status_code=400, detail=f"A senha precisa ter ao menos {minimo} caracteres.")
    if len(senha) > 128:
        raise HTTPException(status_code=400, detail="Senha longa demais (máximo 128 caracteres).")
    n = _norm(senha)
    base = re.sub(r"[\d\W_]+$", "", n)  # "Flamengo2024!" -> "flamengo"
    if n in _COMUNS or base in _COMUNS or re.sub(r"\W", "", n) in _COMUNS:
        raise HTTPException(status_code=400, detail="Essa senha é muito comum. Escolha outra.")
    if len(set(n)) <= 2:
        raise HTTPException(status_code=400, detail="Senha muito repetitiva. Escolha outra.")
    if len(n) >= 6 and any(n in seq * 3 or n in (seq * 3)[::-1] for seq in _SEQUENCIAS):  # "123456789012", "0987654321"
        raise HTTPException(status_code=400, detail="Senha em sequência (ex.: 123456789). Escolha outra.")
    cpf_dig = re.sub(r"\D", "", cpf or "")
    if cpf_dig and (cpf_dig in re.sub(r"\D", "", senha) or cpf_dig[:6] in senha):
        raise HTTPException(status_code=400, detail="A senha não pode conter o seu CPF.")
    local = _norm((email or "").split("@")[0])
    if len(local) >= 4 and local in n:
        raise HTTPException(status_code=400, detail="A senha não pode conter o seu e-mail.")
    for parte in _norm(nome).split():
        if len(parte) >= 4 and parte in n:
            raise HTTPException(status_code=400, detail="A senha não pode conter o seu nome.")
