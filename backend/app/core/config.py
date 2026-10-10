"""
Configuração central da aplicação, lida 100% de variáveis de ambiente (12-factor).

Antes o `.env` existia mas NINGUÉM chamava `load_dotenv()` -- o README mandava
rodar `source .env` na mão (bug #7 da auditoria). Aqui o pydantic-settings carrega
o `.env` automaticamente no import, então `uvicorn app.main:app` já sobe com tudo
configurado, sem passo manual.

Segredos (JWT_SECRET, EMBEDDING_KEY, senha do banco) NUNCA têm default de produção
hardcoded. Em desenvolvimento, se não vierem no ambiente, geramos um valor efêmero
em memória e avisamos no log -- cada reboot invalida tokens antigos, o que é ótimo
pra dev e inaceitável pra produção (por isso o aviso). Em produção esses valores
vêm do Azure Key Vault / variáveis do App Service.
"""

import ipaddress
import secrets
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---------- Banco ----------
    # Sem DATABASE_URL, desenvolvimento usa SQLite local.
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    # ---------- JWT ----------
    jwt_secret: str | None = Field(default=None, alias="JWT_SECRET")
    jwt_algoritmo: str = Field(default="HS256", alias="JWT_ALGORITMO")
    # Emissor e audiência validados em todo token (RFC 8725 §3.8/3.9): um token
    # emitido para outro serviço com o mesmo segredo não é aceito aqui.
    jwt_issuer: str = Field(default="astro-api", alias="JWT_ISSUER")
    jwt_audience: str = Field(default="astro-app", alias="JWT_AUDIENCE")
    # Token intermediário do login (senha ok, falta o rosto). Curto de propósito.
    mfa_token_exp_min: int = Field(default=5, alias="MFA_TOKEN_EXP_MIN")
    # Prova de posse da chave (DPoP, RFC 9449 -- app/core/dpop.py). Obrigatória no
    # login de pessoas; proibido desligar em produção. A janela tolera relógio
    # de aparelho levemente adiantado/atrasado.
    dpop_obrigatorio: bool = Field(default=True, alias="DPOP_OBRIGATORIO")
    # Sessão (SEGURANCA.md item 3): máximo absoluto desde o login (senha + rosto)
    # e queda por inatividade (refresh sem uso). Banco não deixa sessão aberta.
    sessao_max_horas: float = Field(default=12.0, alias="SESSAO_MAX_HORAS")
    sessao_inatividade_min: int = Field(default=30, alias="SESSAO_INATIVIDADE_MIN")
    # Rotas públicas (SEGURANCA.md item 4): por IP, por hora / por 15 min.
    cadastro_max_ip_hora: int = Field(default=10, alias="CADASTRO_MAX_IP_HORA")
    # Recuperação de senha (SECURITY_AUDIT A-16): por IP e por conta, por hora.
    recuperacao_max_ip_hora: int = Field(default=10, alias="RECUPERACAO_MAX_IP_HORA")
    recuperacao_max_conta_hora: int = Field(default=5, alias="RECUPERACAO_MAX_CONTA_HORA")
    recuperacao_token_exp_min: int = Field(default=10, alias="RECUPERACAO_TOKEN_EXP_MIN")
    # Loja, Viagens e pontos (SEGURANCA.md item 6): arquivados no app; aqui ficam
    # desligados (404) para não serem superfície de ataque no pentest.
    beneficios_habilitados: bool = Field(default=False, alias="BENEFICIOS_HABILITADOS")
    refresh_max_ip_15min: int = Field(default=120, alias="REFRESH_MAX_IP_15MIN")
    dpop_janela_seg: int = Field(default=60, alias="DPOP_JANELA_SEG")
    # Access token curto (minutos): se vazar, a janela de uso é pequena.
    access_token_exp_min: int = Field(default=15, alias="ACCESS_TOKEN_EXP_MIN")
    # Refresh token longo (dias): rotacionado a cada uso (ver auth_service).
    refresh_token_exp_dias: int = Field(default=7, alias="REFRESH_TOKEN_EXP_DIAS")

    # ---------- Criptografia do embedding facial (LGPD) ----------
    # Chave Fernet (urlsafe base64, 32 bytes). Ver core/security.py.
    embedding_key: str | None = Field(default=None, alias="EMBEDDING_KEY")

    # ---------- Segurança / limites ----------
    # Tamanho máximo da foto em bytes (base64 decodificado). Fecha o bug #4
    # (foto gigante trava o servidor). 5MB é folgado pra uma selfie de câmera.
    foto_max_bytes: int = Field(default=5 * 1024 * 1024, alias="FOTO_MAX_BYTES")
    # Tentativas de biometria por usuário dentro da janela, antes de bloquear.
    biometria_max_tentativas: int = Field(default=5, alias="BIOMETRIA_MAX_TENTATIVAS")
    biometria_janela_min: int = Field(default=15, alias="BIOMETRIA_JANELA_MIN")
    # Falhas de login por conta A PARTIR DO MESMO IP dentro da janela (trava só esse IP).
    login_max_tentativas: int = Field(default=10, alias="LOGIN_MAX_TENTATIVAS")
    # Falhas por conta somando todos os IPs (ataque distribuído): aí trava a conta. Bem
    # maior que o de cima, para um atacante sozinho não conseguir bloquear a vítima.
    login_max_tentativas_conta: int = Field(default=50, alias="LOGIN_MAX_TENTATIVAS_CONTA")
    login_janela_min: int = Field(default=15, alias="LOGIN_JANELA_MIN")

    # ---------- Split Payment (IBS/CBS - Reforma Tributária) ----------
    # Ano da tabela de transição (split_service.CRONOGRAMA) usado no SIMULADOR
    # quando o cliente não informa um ano. Vazio = ano corrente. Não afeta o split
    # de cobranças reais: ali o valor do imposto vem da própria NF-e.
    split_vigencia: str | None = Field(default=None, alias="SPLIT_VIGENCIA")
    # Acima deste valor (em reais), a transferência exige MFA facial (selfie).
    # Abaixo, basta o JWT. Espelha o LIMITE_FACIAL do design (padrão R$ 500).
    limite_facial_reais: float = Field(default=500.0, alias="LIMITE_FACIAL_REAIS")

    # Admin bootstrap: uma PESSOA com papel admin (sem carteira). Não é mais a
    # conta Governo -- caixa e tributos são contas de sistema separadas (ver
    # db/models.py:ContaSistema). Em produção ADMIN_SENHA é obrigatória.
    admin_email: str = Field(default="admin@payflow.com.br", alias="ADMIN_EMAIL")
    admin_senha: str | None = Field(default=None, alias="ADMIN_SENHA")
    # O admin de operação não tem biometria (não é cliente). Para compensar, em
    # produção ele só entra a partir destes IPs (rede interna/VPN/bastion). Vazio
    # em produção = login de admin DESLIGADO.
    admin_ips_permitidos: str = Field(default="", alias="ADMIN_IPS_PERMITIDOS")

    # ---------- Limites de Pix (Res. BCB 142/2021 e IN BCB 491/2024) ----------
    # Período noturno: das HORA_INICIO às HORA_FIM (horário de Brasília).
    noturno_hora_inicio: int = Field(default=20, alias="NOTURNO_HORA_INICIO")
    noturno_hora_fim: int = Field(default=6, alias="NOTURNO_HORA_FIM")
    # Aparelho ainda não confiável (PF): teto por transação e por dia.
    dispositivo_novo_por_transacao: float = Field(default=200.0, alias="DISPOSITIVO_NOVO_POR_TRANSACAO")
    dispositivo_novo_diario: float = Field(default=1000.0, alias="DISPOSITIVO_NOVO_DIARIO")
    # Aumento de limite pedido pelo cliente só vale depois desta carência.
    limite_carencia_horas: int = Field(default=24, alias="LIMITE_CARENCIA_HORAS")

    # ---------- Risco / bloqueio cautelar ----------
    # Transferência a partir deste valor, para destino com quem a origem nunca
    # transacionou, fica RETIDA no recebedor por até BLOQUEIO_CAUTELAR_HORAS.
    risco_valor_minimo: float = Field(default=1000.0, alias="RISCO_VALOR_MINIMO")
    bloqueio_cautelar_horas: int = Field(default=72, alias="BLOQUEIO_CAUTELAR_HORAS")
    # Prazo para o pagador contestar uma transação (MED).
    contestacao_prazo_dias: int = Field(default=80, alias="CONTESTACAO_PRAZO_DIAS")

    # ---------- Rate limit por IP ----------
    login_max_tentativas_ip: int = Field(default=30, alias="LOGIN_MAX_TENTATIVAS_IP")
    # Proxies cujo X-Forwarded-For é confiável (vírgula; IP ou faixa CIDR, ex.: a sub-rede
    # do Container Apps, onde fica o proxy de entrada). Vazio = ignora o header.
    proxies_confiaveis: str = Field(default="", alias="PROXIES_CONFIAVEIS")
    # Azure Front Door: id do perfil (header X-Azure-FDID, que o Front Door sobrescreve).
    # Quando bate, o IP do cliente vem de X-Azure-ClientIP. Vazio = não usa Front Door.
    front_door_id: str = Field(default="", alias="FRONT_DOOR_ID")
    # Consultas de chave Pix por usuário por hora (anti-varredura, como no DICT).
    consulta_chave_max_hora: int = Field(default=60, alias="CONSULTA_CHAVE_MAX_HORA")

    # ---------- Atestação do aparelho (APK Android, SEGURANCA.md item 10) ----------
    # Pacote do app que pode pedir a chave no Keystore.
    atestacao_pacote: str = Field(default="com.payflow.app", alias="ATESTACAO_PACOTE")
    # SHA-256 (hex, vírgula) do certificado que assina o APK. Vazio = não confere a
    # assinatura (APK de debug do CI, que muda de chave a cada build).
    atestacao_assinaturas: str = Field(default="", alias="ATESTACAO_ASSINATURAS")
    # 1 = login só com chave atestada em hardware (ambiente só de APK; desliga PWA/web).
    atestacao_exigida: bool = Field(default=False, alias="ATESTACAO_EXIGIDA")
    # Lista de revogação da Google (chaves de atestação vazadas). Vazio = não confere.
    atestacao_status_url: str = Field(default="https://android.googleapis.com/attestation/status",
                                      alias="ATESTACAO_STATUS_URL")

    # ---------- Biometria ----------
    # Quantas análises faciais rodam ao mesmo tempo. O resto espera até
    # BIOMETRIA_ESPERA_SEG e recebe 503 -- não deixa a biometria ocupar todas as
    # threads da API.
    biometria_concorrencia: int = Field(default=2, alias="BIOMETRIA_CONCORRENCIA")
    biometria_espera_seg: float = Field(default=10.0, alias="BIOMETRIA_ESPERA_SEG")
    desafio_validade_seg: int = Field(default=120, alias="DESAFIO_VALIDADE_SEG")
    # Motor de reconhecimento: "opencv" (YuNet + SFace + anti-spoof MiniFAS, leve,
    # sem TensorFlow -- padrão) | "deepface" (legado, pesado). BIOMETRIA_STUB=1
    # continua desligando tudo nos testes.
    biometria_motor: str = Field(default="opencv", alias="BIOMETRIA_MOTOR")
    # Pasta dos modelos (.onnx/.task). Em produção vêm embutidos na imagem Docker
    # (MODELOS_DOWNLOAD=0); em dev são baixados uma vez e conferidos por SHA-256.
    modelos_dir: str | None = Field(default=None, alias="MODELOS_DIR")
    modelos_download: bool = Field(default=True, alias="MODELOS_DOWNLOAD")
    # Similaridade de cosseno do SFace para "mesma pessoa". O OpenCV publica 0.363
    # no LFW; num banco preferimos errar para o lado de recusar (falso aceite custa
    # mais caro que pedir de novo), então o padrão é mais rígido.
    face_limiar_cosseno: float = Field(default=0.42, alias="FACE_LIMIAR_COSSENO")
    # Foto de documento é antiga/impressa: o limiar do rosto do documento x selfie é
    # mais baixo (próximo do CALFW/CPLFW) e o caso vai para análise se ficar na faixa.
    face_doc_limiar_cosseno: float = Field(default=0.30, alias="FACE_DOC_LIMIAR_COSSENO")
    # Anti-spoof passivo (MiniFAS): probabilidade mínima de "real". Sem o modelo,
    # produção recusa subir; dev só avisa.
    antispoof_limiar: float = Field(default=0.5, alias="ANTISPOOF_LIMIAR")

    # ---------- KYC / documentos ----------
    # "auto" = Tesseract se o binário existir, senão "sem_ocr" (o documento é
    # validado e comparado com o rosto, mas o texto vai para análise humana) |
    # "tesseract" | "stub" (testes: lê o que foi declarado). stub é recusado em produção.
    documento_provedor: str = Field(default="auto", alias="DOCUMENTO_PROVEDOR")
    kyc_documento_obrigatorio: bool = Field(default=True, alias="KYC_DOCUMENTO_OBRIGATORIO")
    documento_max_bytes: int = Field(default=6 * 1024 * 1024, alias="DOCUMENTO_MAX_BYTES")
    empresa_documento_max_bytes: int = Field(default=10 * 1024 * 1024, alias="EMPRESA_DOCUMENTO_MAX_BYTES")

    # ---------- PJ ----------
    # Grande empresa: acima deste valor a operação precisa de DUAS aprovações de
    # pessoas diferentes (além de quem lançou).
    limite_duas_aprovacoes_reais: float = Field(default=250000.0, alias="LIMITE_DUAS_APROVACOES_REAIS")
    # Operação pendente que ninguém decide expira (não fica aprovável meses depois).
    pendente_validade_horas: int = Field(default=72, ge=1, le=720, alias="PENDENTE_VALIDADE_HORAS")
    # MEI pode ter 1 empregado (LC 123/2006, art. 18-C). O PLP 186/2026 propõe 2 --
    # quando virar lei, basta trocar aqui.
    mei_max_funcionarios: int = Field(default=1, alias="MEI_MAX_FUNCIONARIOS")

    # ---------- Senha ----------
    senha_min: int = Field(default=10, alias="SENHA_MIN")

    # ---------- HTTP ----------
    # /docs e /openapi.json: None = automático (desligado em produção).
    docs_habilitados: bool | None = Field(default=None, alias="DOCS_HABILITADOS")

    # ---------- Consulta de CNPJ ----------
    # "stub" (dev/testes: aceita qualquer CNPJ válido) | "brasilapi" (consulta
    # pública da Receita via brasilapi.com.br).
    cnpj_provedor: str = Field(default="stub", alias="CNPJ_PROVEDOR")

    # ---------- Rendimento ----------
    # CDI anual (fração, ex 0.149 = 14,9% a.a.) e quanto dele a conta paga (1.0 = 100%).
    cdi_anual: float = Field(default=0.149, alias="CDI_ANUAL")
    rendimento_percentual_cdi: float = Field(default=1.0, alias="RENDIMENTO_PERCENTUAL_CDI")

    # ---------- Webhooks ----------
    webhook_timeout_seg: float = Field(default=5.0, alias="WEBHOOK_TIMEOUT_SEG")
    webhook_max_tentativas: int = Field(default=5, alias="WEBHOOK_MAX_TENTATIVAS")
    # Tenta entregar logo após o evento (thread). Os testes desligam e chamam o job.
    webhook_entrega_imediata: bool = Field(default=True, alias="WEBHOOK_ENTREGA_IMEDIATA")

    # ---------- CORS ----------
    # Lista separada por vírgula dos origins liberados. Default restrito ao front
    # local (fecha o bug #17: CORS "*"). Em produção, o domínio publicado.
    cors_origins: str = Field(
        default="http://localhost:8081,http://localhost:8080,http://localhost:3000",
        alias="CORS_ORIGINS",
    )
    # Regex opcional de origins (ex.: "https://.*\.netlify\.app" para o deploy de demonstração,
    # cujo subdomínio muda a cada site). Vazio = só a lista acima.
    cors_origin_regex: str | None = Field(default=None, alias="CORS_ORIGIN_REGEX")

    # ---------- Demonstração ----------
    # Libera POST /pagamentos/depositar-demo: a própria pessoa coloca dinheiro de
    # mentira na conta para testar Pix. Recusado em produção (ver get_settings).
    deposito_demo: bool = Field(default=False, alias="DEPOSITO_DEMO")

    # ---------- Ambiente ----------
    ambiente: str = Field(default="desenvolvimento", alias="AMBIENTE")

    # ---------- Modo de teste da biometria ----------
    # Quando True, o DeepFace NÃO é chamado: o cadastro usa um embedding fixo e a
    # verificação sempre aprova. Serve para rodar o backend num host leve (sem
    # TensorFlow) e testar todo o resto do fluxo. É REFUSADO em produção (ver
    # validação abaixo) -- nunca liga biometria falsa num ambiente real.
    biometria_stub: bool = Field(default=False, alias="BIOMETRIA_STUB")

    @property
    def cors_origins_lista(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def proxies_confiaveis_redes(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        # strict=False: "10.0.0.1" vira 10.0.0.1/32 e "10.20.0.5/23" não derruba o boot.
        return [ipaddress.ip_network(p.strip(), strict=False) for p in self.proxies_confiaveis.split(",") if p.strip()]

    @property
    def atestacao_assinaturas_lista(self) -> set[str]:
        return {a.strip().lower().replace(":", "") for a in self.atestacao_assinaturas.split(",") if a.strip()}

    @property
    def admin_ips_lista(self) -> set[str]:
        return {p.strip() for p in self.admin_ips_permitidos.split(",") if p.strip()}

    @property
    def em_producao(self) -> bool:
        return self.ambiente.lower() in {"producao", "production", "prod"}

    @property
    def docs_ligados(self) -> bool:
        """Swagger/OpenAPI: desligado em produção, a não ser que DOCS_HABILITADOS=1.
        Não é controle de segurança (as rotas existem igual) -- só reduz exposição."""
        return self.docs_habilitados if self.docs_habilitados is not None else not self.em_producao


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.biometria_stub and s.em_producao:
        raise RuntimeError(
            "BIOMETRIA_STUB não pode ser usado em produção -- é um modo de teste "
            "que aprova qualquer rosto. Desligue-o (BIOMETRIA_STUB=0)."
        )
    if s.deposito_demo and s.em_producao:
        raise RuntimeError("DEPOSITO_DEMO não pode ser usado em produção (cria dinheiro do nada).")
    if s.cnpj_provedor == "stub" and s.em_producao:
        raise RuntimeError("CNPJ_PROVEDOR=stub não pode ser usado em produção (aceita qualquer CNPJ).")
    if s.documento_provedor == "stub" and s.em_producao:
        raise RuntimeError("DOCUMENTO_PROVEDOR=stub não pode ser usado em produção (aceita o que foi declarado).")
    if not s.kyc_documento_obrigatorio and s.em_producao:
        raise RuntimeError("KYC_DOCUMENTO_OBRIGATORIO=0 não pode ser usado em produção.")
    if not s.dpop_obrigatorio and s.em_producao:
        raise RuntimeError("DPOP_OBRIGATORIO=0 não pode ser usado em produção (token roubado voltaria a servir).")
    if s.biometria_motor not in ("opencv", "deepface"):
        raise RuntimeError(f"BIOMETRIA_MOTOR desconhecido: {s.biometria_motor!r} (use opencv ou deepface).")
    if s.em_producao:
        _conferir_producao(s)
    return s


def _conferir_producao(s: Settings) -> None:
    """Segredos e CORS de produção conferidos no BOOT (SEGURANCA.md item 8), e não só no
    primeiro uso: um deploy mal configurado nem sobe, em vez de falhar no meio de um login."""
    from sqlalchemy.engine import make_url
    try:
        url = make_url(s.database_url or "")
    except Exception:
        raise RuntimeError("DATABASE_URL válida é obrigatória em produção.") from None
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("DATABASE_URL de produção deve usar PostgreSQL.")
    if url.query.get("sslmode") != "verify-full" or not url.query.get("sslrootcert"):
        raise RuntimeError("DATABASE_URL de produção requer sslmode=verify-full e sslrootcert.")
    if s.jwt_algoritmo != "HS256":
        raise RuntimeError("JWT_ALGORITMO deve ser HS256 nesta implementação.")
    if not s.jwt_secret or len(s.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET ausente ou curto (mínimo 32 caracteres) -- use o Key Vault.")
    try:
        from cryptography.fernet import Fernet

        Fernet((s.embedding_key or "").encode())
    except (ValueError, TypeError):
        raise RuntimeError("EMBEDDING_KEY ausente ou não é uma chave Fernet válida -- use o Key Vault.") from None
    if not s.admin_senha or len(s.admin_senha) < 16:
        raise RuntimeError("ADMIN_SENHA ausente ou curta (mínimo 16 caracteres) -- use o Key Vault.")
    # CORS: só origens exatas e https. Regex (ex.: qualquer *.netlify.app) deixaria qualquer
    # site publicado naquele domínio chamar a API como se fosse o app.
    if s.cors_origin_regex:
        raise RuntimeError("CORS_ORIGIN_REGEX não pode ser usado em produção: liste as origens em CORS_ORIGINS.")
    for origem in s.cors_origins_lista:
        if origem == "*" or not origem.startswith("https://"):
            raise RuntimeError(f"CORS_ORIGINS em produção só aceita origens https exatas (recebido {origem!r}).")
