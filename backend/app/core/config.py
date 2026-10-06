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

import secrets
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---------- Banco ----------
    # Sem DATABASE_URL, a app cai no repositório em memória (ver repositories/__init__.py).
    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    # ---------- JWT ----------
    jwt_secret: str | None = Field(default=None, alias="JWT_SECRET")
    jwt_algoritmo: str = Field(default="HS256", alias="JWT_ALGORITMO")
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
    # Tentativas de login por e-mail dentro da janela.
    login_max_tentativas: int = Field(default=10, alias="LOGIN_MAX_TENTATIVAS")
    login_janela_min: int = Field(default=15, alias="LOGIN_JANELA_MIN")

    # ---------- Split Payment (IBS/CBS - Reforma Tributária) ----------
    # "2026" = alíquotas de teste; "2027" = simulação cheia. As alíquotas em si
    # ficam em split_service.ALIQUOTAS -- aqui só qual vigência está ativa.
    split_vigencia: str = Field(default="2026", alias="SPLIT_VIGENCIA")
    # Acima deste valor (em reais), a transferência exige MFA facial (selfie).
    # Abaixo, basta o JWT. Espelha o LIMITE_FACIAL do design (padrão R$ 500).
    limite_facial_reais: float = Field(default=500.0, alias="LIMITE_FACIAL_REAIS")
    # Conta Governo (destino do imposto + emissor dos depósitos). É criada no boot.
    conta_governo_documento: str = Field(default="GOV-TESOURO", alias="CONTA_GOVERNO_DOCUMENTO")
    conta_governo_carteira_id: int = Field(default=0, alias="CONTA_GOVERNO_CARTEIRA_ID")

    # Admin bootstrap: a conta Governo é também a conta admin (faz depósitos, vê
    # relatórios). Em produção, ADMIN_SENHA é obrigatória (erro se faltar); em dev
    # cai num default com aviso no log.
    admin_email: str = Field(default="admin@payflow.com.br", alias="ADMIN_EMAIL")
    admin_senha: str | None = Field(default=None, alias="ADMIN_SENHA")

    # ---------- CORS ----------
    # Lista separada por vírgula dos origins liberados. Default restrito ao front
    # local (fecha o bug #17: CORS "*"). Em produção, o domínio publicado.
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:19006,http://127.0.0.1:5500",
        alias="CORS_ORIGINS",
    )

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
    def em_producao(self) -> bool:
        return self.ambiente.lower() in {"producao", "production", "prod"}


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.biometria_stub and s.em_producao:
        raise RuntimeError(
            "BIOMETRIA_STUB não pode ser usado em produção -- é um modo de teste "
            "que aprova qualquer rosto. Desligue-o (BIOMETRIA_STUB=0)."
        )
    return s
