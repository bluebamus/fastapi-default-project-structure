"""Auth 도메인 스키마 — 회원가입/토큰 요청·응답."""
from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    """회원가입 요청."""

    username: str = Field(..., min_length=1, max_length=100, description="사용자명(고유)")
    email: str = Field(..., max_length=255, description="이메일")
    password: str = Field(..., min_length=8, max_length=128, description="비밀번호(8자 이상)")


class UserResponse(BaseModel):
    """사용자 응답(민감 정보 제외)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    is_active: bool


class TokenResponse(BaseModel):
    """토큰 응답(OAuth2 bearer)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """토큰 재발급 요청."""

    refresh_token: str = Field(..., description="유효한 Refresh Token")
