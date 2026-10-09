"""
Dependências do FastAPI: autenticação, contexto de conta e aparelho.

- `usuario_atual`: exige access token JWT (Authorization: Bearer).
- `admin_atual`: além disso, papel admin.
- `ip_cliente`: IP real. Só lê X-Forwarded-For quando a conexão vem de um proxy
  listado em PROXIES_CONFIAVEIS -- senão qualquer cliente forjaria o próprio IP.
- `dispositivo_atual`: aparelho do header X-Dispositivo-Id (registrado no login).
- `conta_atual`: carteira em uso. Sem header, a carteira PF da pessoa. Com
  `X-Conta: <numero>`, uma carteira PJ em que a pessoa tem vínculo ativo -- é
  assim que o mesmo login opera a conta pessoal e as empresas.
"""

import hashlib
from datetime import timedelta

import jwt
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import security, tempo
from app.core.config import get_settings
from app.db.models import Papel, PapelVinculo
from app.repositories import get_repository
from app.repositories.repository import Repositorio

_bearer = HTTPBearer(auto_error=False)


def get_repo() -> Repositorio:
    return get_repository()


def ip_cliente(request: Request) -> str | None:
    if not request.client:
        return None
    direto = request.client.host
    confiaveis = get_settings().proxies_confiaveis_lista
    xff = request.headers.get("x-forwarded-for")
    if not xff or direto not in confiaveis:
        return direto
    # Percorre da direita para a esquerda pulando os proxies confiáveis.
    for ip in reversed([p.strip() for p in xff.split(",") if p.strip()]):
        if ip not in confiaveis:
            return ip
    return direto


def hash_dispositivo(dispositivo_id: str) -> str:
    return hashlib.sha256(dispositivo_id.encode("utf-8")).hexdigest()


def usuario_atual(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    repo: Repositorio = Depends(get_repo),
    x_dispositivo_id: str | None = Header(default=None, max_length=128),
) -> dict:
    """Valida o access token e, além da assinatura/expiração:
    - `dev`: o token foi emitido para ESTE aparelho (header X-Dispositivo-Id) --
      token copiado para outro aparelho não funciona;
    - `sid`: a sessão não foi encerrada (Segurança > Sessões) -- cai na hora;
    - o aparelho não está bloqueado (celular roubado)."""
    nao_autorizado = {"WWW-Authenticate": "Bearer"}
    if credenciais is None or not credenciais.credentials:
        raise HTTPException(status_code=401, detail="Autenticação necessária.", headers=nao_autorizado)
    try:
        payload = security.decodificar_token(credenciais.credentials, "access")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.", headers=nao_autorizado)
    dev = payload.get("dev")
    if dev and (not x_dispositivo_id or hash_dispositivo(x_dispositivo_id) != dev):
        raise HTTPException(status_code=401, detail="Sessão emitida para outro aparelho.", headers=nao_autorizado)
    sid = payload.get("sid")
    if sid and not repo.sessao_ativa(sid):
        raise HTTPException(status_code=401, detail="Sessão encerrada. Entre de novo.", headers=nao_autorizado)
    usuario = repo.obter_usuario_por_id(int(payload["sub"]))
    if not usuario or not usuario["ativo"]:
        raise HTTPException(status_code=401, detail="Conta inativa ou inexistente.", headers=nao_autorizado)
    if dev and repo.dispositivo_bloqueado(usuario["id"], dev):
        raise HTTPException(status_code=401, detail="Aparelho bloqueado.", headers=nao_autorizado)
    return {**usuario, "sessao_id": sid}


def usuario_opcional(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    repo: Repositorio = Depends(get_repo),
    x_dispositivo_id: str | None = Header(default=None, max_length=128),
) -> dict | None:
    if credenciais is None or not credenciais.credentials:
        return None
    return usuario_atual(credenciais, repo, x_dispositivo_id)


def admin_atual(usuario: dict = Depends(usuario_atual), ip: str | None = Depends(ip_cliente)) -> dict:
    if usuario["papel"] != Papel.ADMIN.value:
        raise HTTPException(status_code=403, detail="Ação restrita a administradores.")
    s = get_settings()
    permitidos = s.admin_ips_lista
    if (s.em_producao and not permitidos) or (permitidos and ip not in permitidos):
        raise HTTPException(status_code=403, detail="Acesso administrativo não permitido a partir desta rede.")
    return usuario


def dispositivo_atual(
    x_dispositivo_id: str | None = Header(default=None, max_length=128),
    usuario: dict = Depends(usuario_atual),
    repo: Repositorio = Depends(get_repo),
) -> dict | None:
    """Aparelho em uso (registrado como NÃO confiável se for a primeira vez).
    Sem header, None -- tratado como aparelho não confiável nos limites."""
    if not x_dispositivo_id:
        return None
    return repo.registrar_dispositivo(usuario_id=usuario["id"], id_hash=hash_dispositivo(x_dispositivo_id), nome=None)


def conta_atual(
    x_conta: str | None = Header(default=None, max_length=12),
    usuario: dict = Depends(usuario_atual),
    repo: Repositorio = Depends(get_repo),
) -> dict:
    if not x_conta:
        conta = repo.carteira_pf_do_usuario(usuario["id"])
        if not conta:
            raise HTTPException(status_code=404, detail="Você ainda não tem conta pessoal. Use o header X-Conta para operar uma empresa.")
        return {**conta, "vinculo": None}
    conta = repo.obter_conta_por_numero(x_conta)
    if not conta:
        raise HTTPException(status_code=404, detail="Conta não encontrada.")
    if conta["titular_tipo"] == "PF":
        if conta["usuario_id"] != usuario["id"]:
            raise HTTPException(status_code=403, detail="Você não tem acesso a esta conta.")
        return {**conta, "vinculo": None}
    if conta["titular_tipo"] == "PJ":
        vinculo = repo.obter_vinculo(usuario["id"], conta["empresa_id"])
        if not vinculo:
            raise HTTPException(status_code=403, detail="Você não tem acesso a esta empresa.")
        ultimo = vinculo.get("ultimo_acesso_em")
        if ultimo is None or tempo.agora() - ultimo > timedelta(minutes=10):
            repo.marcar_acesso_vinculo(vinculo["id"])
        return {**conta, "vinculo": vinculo}
    raise HTTPException(status_code=403, detail="Conta de sistema não pode ser operada.")


def exigir_papel(conta: dict, *papeis: PapelVinculo) -> None:
    """Para contas PJ: o vínculo precisa ter um dos papéis. Contas PF passam."""
    v = conta.get("vinculo")
    if conta["titular_tipo"] == "PJ" and (v is None or v["papel"] not in {p.value for p in papeis}):
        nomes = ", ".join(p.value for p in papeis)
        raise HTTPException(status_code=403, detail=f"Seu papel nesta empresa não permite esta ação (precisa: {nomes}).")


def exigir_pj(conta: dict) -> None:
    if conta["titular_tipo"] != "PJ":
        raise HTTPException(status_code=400, detail="Esta ação é só para contas de empresa. Envie o header X-Conta com o número da conta PJ.")
