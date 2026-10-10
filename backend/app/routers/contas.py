"""Abertura de conta (PF/PJ), contas, empresa, equipe (convites), convites recebidos e folha."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from app.core.config import get_settings
from app.core.limites import limitar_por_ip
from app.db.models import PapelVinculo
from app.deps import (
    conta_atual,
    dispositivo_atual,
    exigir_papel,
    exigir_pj,
    get_repo,
    hash_dispositivo,
    ip_cliente,
    usuario_atual,
)
from app.repositories.repository import Repositorio
from app.schemas.comum import ContaResponse
from app.schemas.contas import (
    AcaoComBiometria,
    ConviteCreate,
    DocumentoEmpresaEnvio,
    EmpresaCreate,
    EmpresaResponse,
    FolhaPagar,
    FuncionarioCreate,
    PessoaCreate,
    VinculoResponse,
    VinculoUpdate,
)
from app.services import contas_service, equipe_service, folha_service, politica_pj

router = APIRouter(tags=["contas"])


# ------------------------------------------------------------------ abertura de conta


@router.post("/usuarios", response_model=ContaResponse, status_code=201)
def cadastrar_pessoa(
    dados: PessoaCreate,
    repo: Repositorio = Depends(get_repo),
    ip: str | None = Depends(ip_cliente),
    x_dispositivo_id: str | None = Header(default=None, max_length=128),
):
    """Cadastro público da pessoa: dados + prova de vida de CADASTRO (peça antes
    POST /biometria/desafios {"modo": "cadastro"}) + documento de identidade."""
    limitar_por_ip(repo, tipo="limite_cadastro", ip=ip, maximo=get_settings().cadastro_max_ip_hora, janela_min=60,
                   mensagem="Muitas contas abertas a partir desta rede. Tente mais tarde.")
    return contas_service.criar_pessoa(
        repo, nome=dados.nome, email=dados.email, senha=dados.senha, cpf=dados.cpf, prova=dados.biometria,
        dispositivo_hash=hash_dispositivo(x_dispositivo_id) if x_dispositivo_id else None, ip=ip,
        data_nascimento=dados.data_nascimento, celular=dados.celular, documento=dados.documento,
    )


@router.get("/contas", response_model=list[ContaResponse])
def minhas_contas(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    """Contas que a pessoa pode operar: a PF e as das empresas em que tem vínculo ATIVO."""
    return repo.contas_do_usuario(usuario["id"])


@router.get("/contas/atual", response_model=ContaResponse)
def conta_em_uso(conta: dict = Depends(conta_atual)):
    v = conta.get("vinculo")
    return {**conta, "papel": v["papel"] if v else None, "alcada": v["alcada"] if v else None}


@router.post("/empresas", response_model=ContaResponse, status_code=201)
def abrir_empresa(dados: EmpresaCreate, usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo),
                  ip: str | None = Depends(ip_cliente)):
    """Quem abre vira o REPRESENTANTE LEGAL e primeiro admin. Precisa de identidade verificada."""
    conta = contas_service.criar_empresa(
        repo, usuario=usuario, cnpj=dados.cnpj, razao_social=dados.razao_social, nome_fantasia=dados.nome_fantasia,
        porte=dados.porte, regime=dados.regime_apuracao, setor=dados.setor, ip=ip, documentos=dados.documentos,
    )
    return {**conta, "papel": "admin", "alcada": None}


# ------------------------------------------------------------------ empresa em uso


@router.get("/empresas/atual", response_model=EmpresaResponse)
def empresa_em_uso(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    exigir_pj(conta)
    return repo.obter_empresa(conta["empresa_id"])


@router.get("/empresas/atual/politica")
def politica_da_empresa(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    """Regras de acesso do porte (MEI/PME/Grande) + vagas usadas."""
    exigir_pj(conta)
    pol = politica_pj.politica(repo.obter_empresa(conta["empresa_id"])["porte"])
    return {**pol.para_api(), "usuarios_ocupados": repo.contar_vagas_ocupadas(conta["empresa_id"]),
            "funcionarios_ativos": repo.contar_funcionarios_ativos(conta["empresa_id"])}


@router.get("/empresas/atual/documentos")
def documentos_da_empresa(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    return repo.listar_documentos_empresa(conta["empresa_id"])


@router.post("/empresas/atual/documentos", status_code=201)
def enviar_documento(dados: DocumentoEmpresaEnvio, usuario: dict = Depends(usuario_atual),
                     conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo),
                     ip: str | None = Depends(ip_cliente)):
    exigir_pj(conta)
    exigir_papel(conta, PapelVinculo.ADMIN)
    return contas_service.enviar_documento_empresa(repo, conta=conta, usuario=usuario, tipo=dados.tipo,
                                                   arquivo_b64=dados.arquivo, ip=ip)


# ------------------------------------------------------------------ equipe (admin)


@router.get("/empresas/atual/vinculos", response_model=list[VinculoResponse])
def listar_equipe(usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                  repo: Repositorio = Depends(get_repo)):
    return equipe_service.listar(repo, conta=conta, usuario=usuario)


@router.post("/empresas/atual/vinculos", response_model=VinculoResponse, status_code=201)
def convidar(dados: ConviteCreate, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
             repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    """Dá acesso a uma PESSOA pelo CPF. Nasce pendente; ela aceita no próprio app, com o rosto."""
    return equipe_service.convidar(
        repo, conta=conta, autor=usuario, cpf=dados.cpf, nome=dados.nome, email=dados.email, celular=dados.celular,
        cargo=dados.cargo, papel=dados.papel, alcada=dados.alcada, prova=dados.biometria, ip=ip,
    )


@router.patch("/empresas/atual/vinculos/{vinculo_id}", response_model=VinculoResponse)
def alterar_acesso(vinculo_id: int, dados: VinculoUpdate, usuario: dict = Depends(usuario_atual),
                   conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo),
                   ip: str | None = Depends(ip_cliente)):
    return equipe_service.alterar(repo, conta=conta, autor=usuario, vinculo_id=vinculo_id, papel=dados.papel,
                                  alcada=dados.alcada, sem_limite=dados.sem_limite, prova=dados.biometria, ip=ip)


@router.post("/empresas/atual/vinculos/{vinculo_id}/suspender", response_model=VinculoResponse)
def suspender(vinculo_id: int, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
              repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    return equipe_service.mudar_status(repo, conta=conta, autor=usuario, vinculo_id=vinculo_id, acao="suspender",
                                       prova=None, ip=ip)


@router.post("/empresas/atual/vinculos/{vinculo_id}/reativar", response_model=VinculoResponse)
def reativar(vinculo_id: int, dados: AcaoComBiometria, usuario: dict = Depends(usuario_atual),
             conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo),
             ip: str | None = Depends(ip_cliente)):
    return equipe_service.mudar_status(repo, conta=conta, autor=usuario, vinculo_id=vinculo_id, acao="reativar",
                                       prova=dados.biometria, ip=ip)


@router.delete("/empresas/atual/vinculos/{vinculo_id}", response_model=VinculoResponse)
def revogar(vinculo_id: int, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
            repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    return equipe_service.mudar_status(repo, conta=conta, autor=usuario, vinculo_id=vinculo_id, acao="revogar",
                                       prova=None, ip=ip)


@router.get("/empresas/atual/pendentes")
def operacoes_pendentes(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo),
                        status: str | None = "pendente"):
    exigir_pj(conta)
    if conta["vinculo"]["papel"] == PapelVinculo.CONSULTA.value:
        raise HTTPException(status_code=403, detail="Seu papel não permite ver operações pendentes.")
    pendentes = repo.listar_pendentes(conta["empresa_id"], status=status)
    nomes: dict[int, str] = {}
    for p in pendentes:
        uid = p["criado_por_usuario_id"]
        if uid not in nomes:
            u = repo.obter_usuario_por_id(uid)
            nomes[uid] = u["nome"] if u else "—"
        p["criado_por_nome"] = nomes[uid]
    return pendentes


# ------------------------------------------------------------------ convites recebidos (a própria pessoa)


@router.get("/convites")
def meus_convites(usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo)):
    """Convites pendentes para o MEU CPF."""
    return equipe_service.meus_convites(repo, usuario=usuario)


@router.post("/convites/{vinculo_id}/aceitar", response_model=VinculoResponse)
def aceitar_convite(vinculo_id: int, dados: AcaoComBiometria, usuario: dict = Depends(usuario_atual),
                    repo: Repositorio = Depends(get_repo), ip: str | None = Depends(ip_cliente)):
    return equipe_service.aceitar(repo, usuario=usuario, vinculo_id=vinculo_id, prova=dados.biometria, ip=ip)


@router.post("/convites/{vinculo_id}/recusar", status_code=204)
def recusar_convite(vinculo_id: int, usuario: dict = Depends(usuario_atual), repo: Repositorio = Depends(get_repo),
                    ip: str | None = Depends(ip_cliente)):
    equipe_service.recusar(repo, usuario=usuario, vinculo_id=vinculo_id, ip=ip)
    return Response(status_code=204)


# ------------------------------------------------------------------ funcionários e folha


@router.get("/empresas/atual/funcionarios")
def listar_funcionarios(conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo)):
    return folha_service.listar(repo, conta=conta)


@router.post("/empresas/atual/funcionarios", status_code=201)
def cadastrar_funcionario(dados: FuncionarioCreate, usuario: dict = Depends(usuario_atual),
                          conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo),
                          ip: str | None = Depends(ip_cliente)):
    return folha_service.cadastrar(repo, conta=conta, autor=usuario, nome=dados.nome, cpf=dados.cpf, cargo=dados.cargo,
                                   salario=dados.salario, ip=ip)


@router.delete("/empresas/atual/funcionarios/{funcionario_id}", status_code=204)
def desligar_funcionario(funcionario_id: int, usuario: dict = Depends(usuario_atual),
                         conta: dict = Depends(conta_atual), repo: Repositorio = Depends(get_repo),
                         ip: str | None = Depends(ip_cliente)):
    folha_service.desligar(repo, conta=conta, autor=usuario, funcionario_id=funcionario_id, ip=ip)
    return Response(status_code=204)


@router.post("/empresas/atual/folha/pagar")
def pagar_folha(dados: FolhaPagar, usuario: dict = Depends(usuario_atual), conta: dict = Depends(conta_atual),
                dispositivo: dict | None = Depends(dispositivo_atual), repo: Repositorio = Depends(get_repo),
                ip: str | None = Depends(ip_cliente)):
    """Paga salários SÓ para funcionários cadastrados, na conta PF do próprio CPF."""
    return folha_service.pagar(repo, usuario=usuario, conta=conta, dispositivo=dispositivo, itens=dados.itens,
                               descricao=dados.descricao, biometria=dados.biometria, ip=ip)
