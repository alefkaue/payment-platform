from datetime import date, datetime

from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.comum import ProvaBiometrica


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=180, description="E-mail ou CPF.")
    senha: str = Field(..., min_length=1, max_length=128)


class LoginMfaRequest(BaseModel):
    mfa_token: str = Field(..., min_length=20, max_length=2000)
    biometria: ProvaBiometrica
    # APK Android: cadeia de atestação da chave DPoP (base64 DER, folha primeiro).
    atestacao: list[Annotated[str, Field(max_length=8000)]] | None = Field(default=None, max_length=8)


class MfaDesafioRequest(BaseModel):
    mfa_token: str = Field(..., min_length=20, max_length=2000)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, max_length=2000)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expira_em: datetime
    sessao_id: str | None = None


class LoginResponse(BaseModel):
    """Etapa 1 do login. Pessoas sempre recebem mfa_requerido=True (falta o rosto);
    só o admin de operação recebe os tokens direto."""

    mfa_requerido: bool
    mfa_token: str | None = None
    mfa_expira_em: datetime | None = None
    desafio: dict | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str | None = None
    access_expira_em: datetime | None = None
    sessao_id: str | None = None


class TrocarSenhaRequest(BaseModel):
    senha_atual: str = Field(..., min_length=1, max_length=128)
    nova_senha: str = Field(..., min_length=1, max_length=128)
    biometria: ProvaBiometrica


class RecuperacaoRequest(BaseModel):
    login: str = Field(..., min_length=3, max_length=180, description="E-mail ou CPF.")
    data_nascimento: date


class RecuperacaoConcluirRequest(BaseModel):
    recuperacao_token: str = Field(..., min_length=20, max_length=2000)
    biometria: ProvaBiometrica
    nova_senha: str = Field(..., min_length=1, max_length=128)
