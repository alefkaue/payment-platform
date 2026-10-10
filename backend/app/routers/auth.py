"""Login em duas etapas (senha + rosto), sessões e quem sou eu."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from app.core import dpop as dpop_prova
from app.core.config import get_settings
from app.core.limites import limitar_por_ip
from app.deps import get_repo, hash_dispositivo, ip_cliente, usuario_atual
from app.repositories.repository import Repositorio
from app.schemas.auth import LoginMfaRequest, LoginRequest, LoginResponse, MfaDesafioRequest, RefreshRequest, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _ua(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _dev(x_dispositivo_id: str | None) -> str | None:
    return hash_dispositivo(x_dispositivo_id) if x_dispositivo_id else None


def _jkt(request: Request, prova: str | None, repo: Repositorio) -> str | None:
    """Impressão da chave do aparelho, se veio prova DPoP (validada aqui)."""
    if not prova:
        return None
    return dpop_prova.verificar(prova, metodo=request.method, caminho=request.url.path, repo=repo)


@router.post("/login", response_model=LoginResponse)
def login(
    dados: LoginRequest,
    request: Request,
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
    x_dispositivo_id: str | None = Header(default=None, max_length=128),
    dpop: str | None = Header(default=None, alias="DPoP"),
):
    """Etapa 1 (senha). Para pessoas devolve `mfa_token` + desafio de prova de
    vida -- a sessão só é criada em /auth/login/mfa, com o rosto. Exige o header
    DPoP: a chave do aparelho fica amarrada a todos os tokens desta sessão."""
    return auth_service.iniciar_login(repo, email=dados.email, senha=dados.senha, ip=ip,
                                      dispositivo_hash=_dev(x_dispositivo_id), user_agent=_ua(request),
                                      jkt=_jkt(request, dpop, repo))


@router.post("/login/mfa", response_model=TokenResponse)
def login_mfa(
    dados: LoginMfaRequest,
    request: Request,
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
    x_dispositivo_id: str | None = Header(default=None, max_length=128),
    dpop: str | None = Header(default=None, alias="DPoP"),
):
    """Etapa 2 (rosto com prova de vida). No mesmo aparelho e com a mesma chave da etapa 1."""
    return auth_service.concluir_login(repo, mfa_token=dados.mfa_token, prova=dados.biometria, ip=ip,
                                       dispositivo_hash=_dev(x_dispositivo_id), user_agent=_ua(request),
                                       jkt=_jkt(request, dpop, repo))


@router.post("/login/mfa/desafio", status_code=201)
def novo_desafio_mfa(
    dados: MfaDesafioRequest,
    request: Request,
    repo: Repositorio = Depends(get_repo),
    x_dispositivo_id: str | None = Header(default=None, max_length=128),
    dpop: str | None = Header(default=None, alias="DPoP"),
):
    """Nova tentativa da prova de vida dentro do mesmo login (desafio é de uso único)."""
    return auth_service.novo_desafio_mfa(repo, mfa_token=dados.mfa_token, dispositivo_hash=_dev(x_dispositivo_id),
                                         jkt=_jkt(request, dpop, repo))


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    dados: RefreshRequest,
    request: Request,
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
    x_dispositivo_id: str | None = Header(default=None, max_length=128),
    dpop: str | None = Header(default=None, alias="DPoP"),
):
    limitar_por_ip(repo, tipo="limite_refresh", ip=ip, maximo=get_settings().refresh_max_ip_15min, janela_min=15,
                   mensagem="Muitas renovações de sessão a partir desta rede. Tente mais tarde.")
    return auth_service.renovar(repo, refresh_token=dados.refresh_token, ip=ip,
                                dispositivo_hash=_dev(x_dispositivo_id), user_agent=_ua(request),
                                jkt=_jkt(request, dpop, repo))


@router.post("/logout", status_code=204)
def logout(dados: RefreshRequest, repo: Repositorio = Depends(get_repo)):
    auth_service.logout(repo, refresh_token=dados.refresh_token)
    return Response(status_code=204)


@router.get("/eu")
def eu(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    """A pessoa logada e as contas que ela pode operar (PF + empresas)."""
    return {
        "usuario_id": usuario["id"],
        "nome": usuario["nome"],
        "email": usuario["email"],
        "papel": usuario["papel"],
        "tem_biometria": usuario["tem_biometria"],
        "kyc_status": usuario.get("kyc_status"),
        "pontos": usuario["pontos"],
        "contas": repo.contas_do_usuario(usuario["id"]),
    }


# ------------------------------------------------------------------ sessões


@router.get("/sessoes")
def listar_sessoes(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    """Sessões ativas (aparelho, IP, último uso). A atual vem marcada."""
    atual = usuario.get("sessao_id")
    return [{**s, "atual": s["sessao_id"] == atual} for s in repo.listar_sessoes(usuario["id"])]


@router.delete("/sessoes/{sessao_id}", status_code=204)
def encerrar_sessao(sessao_id: str, usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo),
                    ip: str | None = Depends(ip_cliente)):
    if not repo.revogar_sessao(usuario["id"], sessao_id):
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    repo.registrar_log(ator=usuario["email"], acao="sessao_encerrada", ip=ip, usuario_id=usuario["id"])
    return Response(status_code=204)


@router.post("/sessoes/encerrar-outras")
def encerrar_outras(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo),
                    ip: str | None = Depends(ip_cliente)):
    n = repo.revogar_outras_sessoes(usuario["id"], usuario.get("sessao_id"))
    repo.registrar_log(ator=usuario["email"], acao="sessoes_encerradas", ip=ip, usuario_id=usuario["id"],
                       detalhe={"quantidade": n})
    return {"encerradas": n}
