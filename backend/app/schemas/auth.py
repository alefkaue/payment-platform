from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.comum import ProvaBiometrica


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=180, description="E-mail ou CPF.")
    senha: str = Field(..., min_length=1, max_length=128)


class LoginMfaRequest(BaseModel):
    mfa_token: str = Field(..., min_length=20, max_length=2000)
    biometria: ProvaBiometrica


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
