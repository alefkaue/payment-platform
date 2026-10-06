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
    # Proxies cujo X-Forwarded-For é confiável (vírgula). Vazio = ignora o header.
    proxies_confiaveis: str = Field(default="", alias="PROXIES_CONFIAVEIS")
    # Consultas de chave Pix por usuário por hora (anti-varredura, como no DICT).
    consulta_chave_max_hora: int = Field(default=60, alias="CONSULTA_CHAVE_MAX_HORA")

    # ---------- Biometria ----------
    # Quantas análises faciais (DeepFace) rodam ao mesmo tempo. O resto espera até
    # BIOMETRIA_ESPERA_SEG e recebe 503 -- não deixa a biometria ocupar todas as
    # threads da API.
    biometria_concorrencia: int = Field(default=2, alias="BIOMETRIA_CONCORRENCIA")
    biometria_espera_seg: float = Field(default=10.0, alias="BIOMETRIA_ESPERA_SEG")
    desafio_validade_seg: int = Field(default=120, alias="DESAFIO_VALIDADE_SEG")

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
    def proxies_confiaveis_lista(self) -> set[str]:
        return {p.strip() for p in self.proxies_confiaveis.split(",") if p.strip()}

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
    if s.cnpj_provedor == "stub" and s.em_producao:
        raise RuntimeError("CNPJ_PROVEDOR=stub não pode ser usado em produção (aceita qualquer CNPJ).")
    return s
