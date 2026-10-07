from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.comum import ProvaBiometrica


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=180, description="E-mail ou CPF.")
    senha: str = Field(..., min_length=1, max_length=72)


class LoginBiometriaRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=180, description="E-mail ou CPF.")
    biometria: ProvaBiometrica


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expira_em: datetime
