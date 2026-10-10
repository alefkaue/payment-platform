"""
Autenticação: login da PESSOA com DOIS fatores obrigatórios.

  1. POST /auth/login {email|cpf, senha}            -> algo que você SABE
     senha confere -> devolve um `mfa_token` (5 min, preso a este aparelho) e um
     desafio de prova de vida (modo "login": piscar 3x). NENHUM token de acesso.
  2. POST /auth/login/mfa {mfa_token, biometria}   -> algo que você É
     rosto confere com o cadastro, com prova de vida feita AGORA -> sessão.

Não existe mais "entrar só com a biometria" nem "só com a senha" (exceto o admin
de operação, que não é cliente: ver ADMIN_IPS_PERMITIDOS).

Sessão (OWASP ASVS V7 / RFC 8725):
- access token curto, com `dev` (hash do aparelho) e `sid` (sessão): token
  copiado para outro aparelho não funciona; encerrar a sessão derruba na hora;
- refresh token rotacionado a cada uso, com detecção de reuso (reuso = roubo:
  derruba todas as sessões da pessoa) e preso ao aparelho de origem;
- o aparelho em que o rosto foi verificado vira CONFIÁVEL (é o cadastro do
  aparelho, como fazem os bancos num celular novo); aparelho BLOQUEADO não entra.
- Rate limit duplo (por login e por IP) e tempo constante para e-mail inexistente.
"""

import logging
import secrets
import time
from datetime import timedelta
from functools import lru_cache

import jwt
from fastapi import HTTPException

from app.core import dpop, security, tempo
from app.core.config import get_settings
from app.repositories.repository import Repositorio

logger = logging.getLogger("payflow.auth")


@lru_cache
def _hash_falso() -> str:
    """Hash Argon2 de uma senha aleatória: o login de e-mail inexistente gasta o
    mesmo tempo que um de verdade (não revela quais e-mails têm conta)."""
    return security.hash_senha(secrets.token_urlsafe(16))


def _checar_rate_limit(repo: Repositorio, ref: str, ip: str | None) -> None:
    s = get_settings()
    desde = tempo.agora() - timedelta(minutes=s.login_janela_min)
    # Por conta + IP: quem erra a senha de alguém trava a si mesmo, não a vítima.
    # Por conta (todos os IPs, teto maior): senha distribuída por muitos IPs também para.
    # As duas ficam na trilha da própria pessoa.
    por_ip = ip is not None and repo.contar_eventos(tipo="login", desde=desde, referencia=ref, ip=ip) >= s.login_max_tentativas
    if por_ip or repo.contar_eventos(tipo="login", desde=desde, referencia=ref) >= s.login_max_tentativas_conta:
        alvo = repo.obter_usuario_por_login(ref)
        if alvo:
            repo.registrar_log(ator=ref, acao="login_bloqueado_tentativas", ip=ip, usuario_id=alvo["id"])
        raise HTTPException(status_code=429, detail="Muitas tentativas de login. Tente novamente em alguns minutos.",
                            headers={"Retry-After": str(s.login_janela_min * 60)})
    if ip and repo.contar_eventos(tipo="login", desde=desde, ip=ip) >= s.login_max_tentativas_ip:
        raise HTTPException(status_code=429, detail="Muitas tentativas de login a partir desta rede. Tente mais tarde.")


def _checar_admin(ip: str | None) -> None:
    s = get_settings()
    permitidos = s.admin_ips_lista
    if s.em_producao and not permitidos:
        raise HTTPException(status_code=403, detail="Acesso administrativo desabilitado neste ambiente.")
    if permitidos and ip not in permitidos:
        raise HTTPException(status_code=403, detail="Acesso administrativo não permitido a partir desta rede.")


def autenticar(repo: Repositorio, *, email: str, senha: str, ip: str | None = None) -> dict:
    """Confere a senha (fator 1). Não emite sessão."""
    identificador = email.lower().strip()
    usuario = repo.obter_usuario_por_login(identificador)
    # E-mail e CPF (pontuado ou não) são aliases da mesma identidade. Não
    # permitem contornar o rate limit alternando a forma de login.
    ref = usuario["email"] if usuario else identificador
    _checar_rate_limit(repo, ref, ip)
    ok = False
    if usuario and usuario["ativo"]:
        ok = security.verificar_senha(senha, usuario["senha_hash"])
    else:
        security.verificar_senha(senha, _hash_falso())  # tempo parecido
    if not ok:
        repo.registrar_sessao_mfa(tipo="login", sucesso=False, referencia=ref, ip=ip,
                                  usuario_id=usuario["id"] if usuario else None)
        raise HTTPException(status_code=401, detail="E-mail/CPF ou senha inválidos.")
    if security.precisa_rehash(usuario["senha_hash"]):
        # Migração transparente bcrypt -> Argon2id (ou parâmetros novos).
        repo.atualizar_senha_hash(usuario["id"], security.hash_senha(senha))
    return usuario


def _exigir_jkt(jkt: str | None) -> None:
    """Sem prova de posse da chave (DPoP) não há login: o token nasceria sem
    amarração e voltaria a servir para quem o roubasse (SEGURANCA.md item 2)."""
    if jkt is None and get_settings().dpop_obrigatorio:
        raise HTTPException(status_code=400, detail="Envie a prova de posse da chave (header DPoP). Atualize o app.")


def iniciar_login(repo: Repositorio, *, email: str, senha: str, ip: str | None, dispositivo_hash: str | None,
                  user_agent: str | None, jkt: str | None = None) -> dict:
    from app.services import biometria_service

    _exigir_jkt(jkt)
    usuario = autenticar(repo, email=email, senha=senha, ip=ip)
    ref = email.lower().strip()
    if dispositivo_hash and repo.dispositivo_bloqueado(usuario["id"], dispositivo_hash):
        repo.registrar_sessao_mfa(tipo="login", sucesso=False, referencia=ref, ip=ip, usuario_id=usuario["id"],
                                  detalhe={"motivo": "aparelho_bloqueado"})
        raise HTTPException(status_code=403, detail="Este aparelho foi bloqueado. Entre por outro aparelho para desbloquear.")

    if usuario["papel"] == "admin":
        _checar_admin(ip)
        if get_settings().admin_totp_segredo:
            # 2º fator do admin: código do app autenticador (A-15).
            mfa_token, _, exp = security.criar_mfa_token(usuario["id"], dispositivo_hash=dispositivo_hash, jkt=jkt,
                                                         fator="totp")
            repo.registrar_sessao_mfa(tipo="login_senha", sucesso=True, usuario_id=usuario["id"], referencia=ref, ip=ip)
            return {"mfa_requerido": True, "mfa_token": mfa_token, "mfa_expira_em": exp, "desafio": None,
                    "fator": "totp"}
        repo.registrar_sessao_mfa(tipo="login", sucesso=True, usuario_id=usuario["id"], referencia=ref, ip=ip)
        repo.registrar_log(ator=usuario["email"], acao="login_admin", ip=ip, usuario_id=usuario["id"])
        disp = repo.registrar_dispositivo(usuario_id=usuario["id"], id_hash=dispositivo_hash, nome=None) if dispositivo_hash else None
        return {"mfa_requerido": False, **emitir_tokens(repo, usuario, dispositivo=disp, dispositivo_hash=dispositivo_hash,
                                                       ip=ip, user_agent=user_agent, jkt=jkt)}

    if not usuario["tem_biometria"]:
        raise HTTPException(status_code=403, detail="Sua conta não tem biometria cadastrada. Procure o atendimento.")
    mfa_token, _, exp = security.criar_mfa_token(usuario["id"], dispositivo_hash=dispositivo_hash, jkt=jkt)
    desafio = biometria_service.criar_desafio(repo, usuario_id=usuario["id"], modo="login")
    repo.registrar_sessao_mfa(tipo="login_senha", sucesso=True, usuario_id=usuario["id"], referencia=ref, ip=ip)
    return {"mfa_requerido": True, "mfa_token": mfa_token, "mfa_expira_em": exp, "desafio": desafio, "fator": "rosto"}


def _usuario_do_mfa(repo: Repositorio, mfa_token: str, dispositivo_hash: str | None,
                    jkt: str | None = None, fator: str = "rosto") -> tuple[dict, dict]:
    try:
        payload = security.decodificar_token(mfa_token, "mfa")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Etapa de verificação expirada. Entre de novo com a senha.")
    # Token sem `fator` (emitido antes do A-15) era sempre de rosto.
    if payload.get("fator", "rosto") != fator:
        raise HTTPException(status_code=401, detail="Esta etapa de verificação é de outro tipo. Entre de novo.")
    if payload.get("dev") != dispositivo_hash:
        raise HTTPException(status_code=401, detail="A verificação precisa ser concluída no mesmo aparelho.")
    if dpop.jkt_do_token(payload) != jkt:
        raise HTTPException(status_code=401, detail="A verificação precisa ser concluída com a mesma chave do aparelho.")
    if repo.contar_eventos(tipo="mfa_usado", desde=tempo.agora() - timedelta(hours=1), sucesso=True,
                           referencia=payload["jti"]):
        raise HTTPException(status_code=401, detail="Esta etapa de verificação já foi usada. Entre de novo.")
    usuario = repo.obter_usuario_por_id(int(payload["sub"]))
    if not usuario or not usuario["ativo"]:
        raise HTTPException(status_code=401, detail="Conta inativa.")
    return usuario, payload


def novo_desafio_mfa(repo: Repositorio, *, mfa_token: str, dispositivo_hash: str | None,
                     jkt: str | None = None) -> dict:
    """Outra tentativa da prova de vida dentro do mesmo login (o desafio é de uso único)."""
    from app.services import biometria_service

    usuario, _ = _usuario_do_mfa(repo, mfa_token, dispositivo_hash, jkt)
    return biometria_service.criar_desafio(repo, usuario_id=usuario["id"], modo="login")


def _conferir_atestacao(repo: Repositorio, usuario: dict, certificados: list[str] | None, *, jkt: str | None,
                        ip: str | None) -> str | None:
    """Nível da atestação da chave (APK Android) ou None. Atestação forjada, de outra
    chave ou de outro app derruba o login; aparelho com root/emulador só fica sem nível
    (e é recusado se ATESTACAO_EXIGIDA)."""
    from app.core import atestacao

    s = get_settings()
    motivo = "sem atestação (navegador ou PWA)"
    nivel = None
    if certificados:
        try:
            r = atestacao.verificar(certificados, jkt=jkt)
        except atestacao.AtestacaoInvalida as e:
            repo.registrar_sessao_mfa(tipo="login", sucesso=False, referencia=usuario["email"], ip=ip,
                                      usuario_id=usuario["id"], detalhe={"etapa": "atestacao", "motivo": str(e)})
            raise HTTPException(status_code=403, detail="Não foi possível confirmar a segurança deste aparelho.") from None
        nivel, motivo = r.nivel, r.motivo
    if nivel is None and s.atestacao_exigida:
        repo.registrar_sessao_mfa(tipo="login", sucesso=False, referencia=usuario["email"], ip=ip,
                                  usuario_id=usuario["id"], detalhe={"etapa": "atestacao", "motivo": motivo})
        raise HTTPException(status_code=403, detail="Entre pelo app Astro num aparelho sem root e com o sistema original.")
    return nivel


def concluir_login(repo: Repositorio, *, mfa_token: str, prova, ip: str | None, dispositivo_hash: str | None,
                   user_agent: str | None, jkt: str | None = None, atestacao: list[str] | None = None) -> dict:
    from app.services import seguranca_service

    usuario, payload = _usuario_do_mfa(repo, mfa_token, dispositivo_hash, jkt)
    ref = usuario["email"]
    # Antes do rosto: aparelho que não passa nem gasta tentativa de biometria.
    nivel_atestacao = _conferir_atestacao(repo, usuario, atestacao, jkt=jkt, ip=ip)
    try:
        verificacao = seguranca_service.verificar_rosto(repo, usuario=usuario, prova=prova, ip=ip, tipo="login")
    except HTTPException:
        repo.registrar_sessao_mfa(tipo="login", sucesso=False, referencia=ref, ip=ip, usuario_id=usuario["id"],
                                  detalhe={"etapa": "rosto"})
        raise
    if not repo.registrar_sessao_mfa(tipo="mfa_usado", sucesso=True, referencia=payload["jti"], usuario_id=usuario["id"], ip=ip):
        raise HTTPException(status_code=401, detail="Esta etapa de verificação já foi usada. Entre de novo.")
    repo.registrar_sessao_mfa(tipo="login", sucesso=True, usuario_id=usuario["id"], referencia=ref, ip=ip)
    disp = None
    if dispositivo_hash and repo.obter_dispositivo(usuario["id"], dispositivo_hash) is None:
        # Aparece em Segurança > Atividade: a pessoa vê se alguém entrou de outro lugar.
        repo.registrar_log(ator=usuario["email"], acao="login_aparelho_novo", ip=ip, usuario_id=usuario["id"],
                           detalhe={"aparelho": _nome_aparelho(user_agent)})
    if dispositivo_hash:
        # Rosto verificado NESTE aparelho = aparelho cadastrado/confiável.
        disp = repo.registrar_dispositivo(usuario_id=usuario["id"], id_hash=dispositivo_hash, nome=_nome_aparelho(user_agent),
                                          confiavel=True, atestacao=nivel_atestacao, atualizar_atestacao=True)
    repo.registrar_log(ator=usuario["email"], acao="login", ip=ip, usuario_id=usuario["id"],
                       detalhe={"fatores": ["senha", "rosto"], "similaridade": verificacao.get("similaridade"),
                                "dispositivo_id": disp["id"] if disp else None, "atestacao": nivel_atestacao})
    return emitir_tokens(repo, usuario, dispositivo=disp, dispositivo_hash=dispositivo_hash, ip=ip, user_agent=user_agent,
                         jkt=jkt)


def concluir_login_totp(repo: Repositorio, *, mfa_token: str, codigo: str, ip: str | None,
                        dispositivo_hash: str | None, user_agent: str | None, jkt: str | None = None) -> dict:
    """2º fator do admin: código de 6 dígitos do app autenticador (A-15). Cada código
    vale uma vez (não dá para reaproveitar o que alguém viu na tela)."""
    from app.core import totp

    usuario, payload = _usuario_do_mfa(repo, mfa_token, dispositivo_hash, jkt, fator="totp")
    segredo = get_settings().admin_totp_segredo
    if usuario["papel"] != "admin" or not segredo:
        raise HTTPException(status_code=401, detail="Etapa de verificação inválida. Entre de novo.")
    _checar_admin(ip)
    ref = usuario["email"]
    _checar_rate_limit(repo, ref, ip)  # código errado conta como erro de login
    passo = totp.passo_do_codigo(segredo, codigo, _relogio())
    usado = f"totp:{usuario['id']}:{passo}"
    if passo is None or not repo.registrar_sessao_mfa(tipo="mfa_usado", sucesso=True, referencia=usado,
                                                      usuario_id=usuario["id"], ip=ip):
        repo.registrar_sessao_mfa(tipo="login", sucesso=False, referencia=ref, ip=ip, usuario_id=usuario["id"],
                                  detalhe={"etapa": "totp"})
        raise HTTPException(status_code=401, detail="Código inválido ou já usado. Use o próximo código do app.")
    if not repo.registrar_sessao_mfa(tipo="mfa_usado", sucesso=True, referencia=payload["jti"],
                                     usuario_id=usuario["id"], ip=ip):
        raise HTTPException(status_code=401, detail="Esta etapa de verificação já foi usada. Entre de novo.")
    repo.registrar_sessao_mfa(tipo="login", sucesso=True, usuario_id=usuario["id"], referencia=ref, ip=ip)
    repo.registrar_log(ator=ref, acao="login_admin", ip=ip, usuario_id=usuario["id"],
                       detalhe={"fatores": ["senha", "totp"]})
    disp = repo.registrar_dispositivo(usuario_id=usuario["id"], id_hash=dispositivo_hash,
                                      nome=None) if dispositivo_hash else None
    return emitir_tokens(repo, usuario, dispositivo=disp, dispositivo_hash=dispositivo_hash, ip=ip,
                         user_agent=user_agent, jkt=jkt)


def _nome_aparelho(user_agent: str | None) -> str | None:
    """Rótulo amigável para a lista de aparelhos ("Chrome — Windows")."""
    if not user_agent:
        return None
    ua = user_agent.lower()
    so = next((n for k, n in (("android", "Android"), ("iphone", "iPhone"), ("ipad", "iPad"), ("windows", "Windows"),
                              ("mac os", "macOS"), ("linux", "Linux")) if k in ua), "Aparelho")
    nav = next((n for k, n in (("edg/", "Edge"), ("chrome/", "Chrome"), ("firefox/", "Firefox"), ("safari/", "Safari"))
                if k in ua), "Navegador")
    return f"{nav} — {so}"


def emitir_tokens(repo: Repositorio, usuario: dict, *, dispositivo: dict | None = None,
                  dispositivo_hash: str | None = None, ip: str | None = None, user_agent: str | None = None,
                  sessao_id: str | None = None, jkt: str | None = None, auth_time: int | None = None,
                  token_anterior: str | None = None) -> dict:
    sid = sessao_id or security.novo_sessao_id()
    auth_time = auth_time or int(_relogio())  # login novo: a sessão começa agora
    access, access_exp = security.criar_access_token(usuario["id"], usuario["papel"], dispositivo_hash=dispositivo_hash,
                                                     sessao_id=sid, jkt=jkt, auth_time=auth_time)
    refresh_bruto, jti, refresh_exp = security.criar_refresh_token(usuario["id"], sessao_id=sid, jkt=jkt,
                                                                   auth_time=auth_time)
    salvo = repo.salvar_refresh(usuario_id=usuario["id"], jti=jti, token_hash=security.hash_refresh(refresh_bruto),
                        expira_em=refresh_exp, sessao_id=sid, dispositivo_id=dispositivo["id"] if dispositivo else None,
                        ip=ip, user_agent=user_agent, token_anterior=token_anterior)
    if not salvo:
        repo.registrar_log(ator=str(usuario["id"]), acao="refresh_reuso_detectado", ip=ip, usuario_id=usuario["id"])
        raise HTTPException(status_code=401, detail="Sessão inválida. Entre de novo.")
    return {"access_token": access, "refresh_token": refresh_bruto, "token_type": "bearer",
            "access_expira_em": access_exp, "sessao_id": sid}


def _relogio() -> float:
    """Relógio REAL (o JWT também usa o real). Separado para os testes adiantarem."""
    return time.time()


def _checar_limites_da_sessao(payload: dict) -> None:
    """Relógio real (o mesmo do JWT). Sessão sem `auth_time` (emitida antes) usa o iat."""
    s = get_settings()
    agora = _relogio()
    inicio = payload.get("auth_time") or payload["iat"]
    if agora - inicio > s.sessao_max_horas * 3600:
        raise HTTPException(status_code=401, detail="Sua sessão chegou ao tempo máximo. Entre de novo com senha e rosto.")
    # O refresh é trocado a cada renovação: o iat dele marca o último uso da sessão.
    if agora - payload["iat"] > s.sessao_inatividade_min * 60:
        raise HTTPException(status_code=401, detail="Sessão encerrada por inatividade. Entre de novo.")


def renovar(repo: Repositorio, *, refresh_token: str, ip: str | None = None, dispositivo_hash: str | None = None,
            user_agent: str | None = None, jkt: str | None = None) -> dict:
    try:
        payload = security.decodificar_token(refresh_token, "refresh")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre de novo.")
    # Refresh roubado não renova sem a chave do aparelho que fez o login.
    jkt_sessao = dpop.jkt_do_token(payload)
    if jkt_sessao != jkt or (jkt_sessao is None and get_settings().dpop_obrigatorio):
        raise HTTPException(status_code=401, detail="Esta sessão pertence a outro aparelho. Entre de novo.")
    _checar_limites_da_sessao(payload)
    registro = repo.obter_refresh(security.hash_refresh(refresh_token))
    if not registro:
        raise HTTPException(status_code=401, detail="Sessão não reconhecida.")
    if registro["revogado"]:
        logger.warning("Reuso de refresh token detectado (usuario_id=%s). Revogando todas as sessões.", registro["usuario_id"])
        repo.revogar_todos_refresh(registro["usuario_id"])
        repo.registrar_log(ator=str(registro["usuario_id"]), acao="refresh_reuso_detectado", ip=ip,
                           usuario_id=registro["usuario_id"])
        raise HTTPException(status_code=401, detail="Sessão inválida. Entre de novo.")
    usuario = repo.obter_usuario_por_id(registro["usuario_id"])
    if not usuario or not usuario["ativo"]:
        raise HTTPException(status_code=401, detail="Conta inativa.")
    disp = repo.dispositivo_por_id(registro["dispositivo_id"]) if registro["dispositivo_id"] else None
    if disp is not None:
        if disp["id_hash"] != dispositivo_hash:
            raise HTTPException(status_code=401, detail="Esta sessão pertence a outro aparelho.")
        if disp["bloqueado"]:
            raise HTTPException(status_code=401, detail="Aparelho bloqueado.")
    novos = emitir_tokens(repo, usuario, dispositivo=disp, dispositivo_hash=dispositivo_hash if disp else None,
                          ip=ip, user_agent=user_agent, sessao_id=registro["sessao_id"] or payload.get("sid"), jkt=jkt,
                          auth_time=payload.get("auth_time"), token_anterior=security.hash_refresh(refresh_token))
    return novos


# ----------------------------------------------------------- senha (A-16)


def trocar_senha(repo: Repositorio, *, usuario: dict, senha_atual: str, nova_senha: str, prova,
                 ip: str | None) -> dict:
    """Troca com a pessoa logada: senha atual + rosto com prova de vida. As outras
    sessões caem (quem tinha a senha antiga não continua dentro)."""
    from app.services import senha_policy, seguranca_service

    u = repo.obter_usuario_por_id(usuario["id"])
    if not u or not u["ativo"]:
        raise HTTPException(status_code=401, detail="Conta inativa.")
    # Errar a senha atual conta como erro de login: este caminho não dribla o limite.
    _checar_rate_limit(repo, u["email"], ip)
    if not security.verificar_senha(senha_atual, u["senha_hash"]):
        repo.registrar_sessao_mfa(tipo="login", sucesso=False, referencia=u["email"], ip=ip, usuario_id=u["id"],
                                  detalhe={"etapa": "troca_senha"})
        raise HTTPException(status_code=401, detail="Senha atual incorreta.")
    if nova_senha == senha_atual:
        raise HTTPException(status_code=400, detail="A nova senha precisa ser diferente da atual.")
    senha_policy.validar(nova_senha, email=u["email"], cpf=u["cpf"] or "", nome=u["nome"])
    seguranca_service.verificar_rosto(repo, usuario=u, prova=prova, ip=ip, tipo="troca_senha")
    repo.atualizar_senha_hash(u["id"], security.hash_senha(nova_senha))
    encerradas = repo.revogar_outras_sessoes(u["id"], usuario.get("sessao_id"))
    repo.registrar_log(ator=u["email"], acao="senha_alterada", ip=ip, usuario_id=u["id"],
                       detalhe={"sessoes_encerradas": encerradas})
    return {"sessoes_encerradas": encerradas}


def _checar_limite_recuperacao(repo: Repositorio, ref: str, ip: str | None) -> None:
    s = get_settings()
    desde = tempo.agora() - timedelta(hours=1)
    if (ip and repo.contar_eventos(tipo="recuperacao", desde=desde, sucesso=None, ip=ip) >= s.recuperacao_max_ip_hora) \
            or repo.contar_eventos(tipo="recuperacao", desde=desde, sucesso=None, referencia=ref) >= s.recuperacao_max_conta_hora:
        raise HTTPException(status_code=429, detail="Muitos pedidos de recuperação. Tente novamente mais tarde.",
                            headers={"Retry-After": "3600"})


def iniciar_recuperacao(repo: Repositorio, *, login: str, data_nascimento, ip: str | None,
                        dispositivo_hash: str | None, jkt: str | None = None) -> dict:
    """Etapa 1 da recuperação: e-mail/CPF + data de nascimento. A resposta é SEMPRE
    a mesma (token + desafio de prova de vida completo), exista a conta ou não: quem
    só conhece um e-mail não descobre nada. Quem confirma é o rosto, na etapa 2."""
    from app.services import biometria_service

    _exigir_jkt(jkt)
    identificador = login.lower().strip()
    usuario = repo.obter_usuario_por_login(identificador)
    ref = usuario["email"] if usuario else identificador
    _checar_limite_recuperacao(repo, ref, ip)
    confere = bool(usuario and usuario["ativo"] and usuario["tem_biometria"] and usuario["papel"] != "admin"
                   and usuario["data_nascimento"] is not None and usuario["data_nascimento"] == data_nascimento)
    alvo = usuario["id"] if confere else None
    repo.registrar_sessao_mfa(tipo="recuperacao", sucesso=confere, referencia=ref, ip=ip,
                              usuario_id=usuario["id"] if usuario else None)
    if confere:
        repo.registrar_log(ator=ref, acao="recuperacao_senha_pedida", ip=ip, usuario_id=usuario["id"])
    token, _, exp = security.criar_recuperacao_token(alvo, dispositivo_hash=dispositivo_hash, jkt=jkt)
    # Desafio de CADASTRO (todas as ações, embaralhadas): mais forte que o do login.
    desafio = biometria_service.criar_desafio(repo, usuario_id=alvo, modo="cadastro")
    return {"recuperacao_token": token, "expira_em": exp, "desafio": desafio}


_RECUPERACAO_RECUSADA = "Não foi possível confirmar a sua identidade. Comece a recuperação de novo."


def concluir_recuperacao(repo: Repositorio, *, recuperacao_token: str, prova, nova_senha: str, ip: str | None,
                         dispositivo_hash: str | None, jkt: str | None = None) -> None:
    """Etapa 2: rosto com prova de vida no MESMO aparelho e chave da etapa 1. Troca a
    senha e derruba TODAS as sessões (se alguém tinha a senha, perde o acesso)."""
    from app.services import senha_policy, seguranca_service

    try:
        payload = security.decodificar_token(recuperacao_token, "recuperacao")
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status_code=401, detail="A recuperação expirou. Comece de novo.")
    if payload.get("dev") != dispositivo_hash or dpop.jkt_do_token(payload) != jkt:
        raise HTTPException(status_code=401, detail="Conclua a recuperação no mesmo aparelho em que ela começou.")
    usuario_id = security.usuario_da_recuperacao(payload)
    usuario = repo.obter_usuario_por_id(usuario_id) if usuario_id else None
    if not usuario or not usuario["ativo"]:
        raise HTTPException(status_code=401, detail=_RECUPERACAO_RECUSADA)
    # Antes do rosto, para não gastar tentativa de biometria com senha que não serve.
    senha_policy.validar(nova_senha, email=usuario["email"], cpf=usuario["cpf"] or "", nome=usuario["nome"])
    try:
        seguranca_service.verificar_rosto(repo, usuario=usuario, prova=prova, ip=ip, tipo="recuperacao_senha")
    except HTTPException as e:
        if e.status_code == 429:
            raise
        raise HTTPException(status_code=401, detail=_RECUPERACAO_RECUSADA) from None
    if not repo.registrar_sessao_mfa(tipo="mfa_usado", sucesso=True, referencia=payload["jti"],
                                     usuario_id=usuario["id"], ip=ip):
        raise HTTPException(status_code=401, detail="Esta recuperação já foi usada. Comece de novo.")
    repo.atualizar_senha_hash(usuario["id"], security.hash_senha(nova_senha))
    repo.revogar_todos_refresh(usuario["id"])
    repo.registrar_log(ator=usuario["email"], acao="senha_recuperada", ip=ip, usuario_id=usuario["id"])


def logout(repo: Repositorio, *, refresh_token: str) -> None:
    """Encerra a SESSÃO inteira (a família de refresh), não só o token atual."""
    try:
        payload = security.decodificar_token(refresh_token, "refresh")
    except (jwt.PyJWTError, ValueError):
        return
    if payload.get("sid"):
        repo.revogar_sessao(int(payload["sub"]), payload["sid"])
    else:
        repo.revogar_refresh(payload["jti"])
