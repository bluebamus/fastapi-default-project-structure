"""Auth 도메인 스키마 — 회원가입/토큰 요청·응답."""

from pydantic import BaseModel, ConfigDict, Field

from app.utils.validators import EMAIL_PATTERN


class RegisterRequest(BaseModel):
    """회원가입 요청."""

    username: str = Field(..., min_length=1, max_length=100, description="사용자명(고유)")
    email: str = Field(..., max_length=255, pattern=EMAIL_PATTERN, description="이메일")
    password: str = Field(..., min_length=8, max_length=128, description="비밀번호(8자 이상)")


class AuthUserResponse(BaseModel):
    """인증 결과로 반환하는 사용자 정보(비밀번호 해시 등 민감 정보 제외).

    이름에 ``Auth`` 를 붙인 이유: User 도메인에도 ``UserResponse`` 가 있어 같은 이름을 쓰면
    FastAPI 가 OpenAPI 스키마 키를 모듈 경로로 뭉개(``app__features__auth__...__UserResponse``)
    문서에 그대로 노출된다. 공개 스키마 이름은 프로젝트 전역에서 고유해야 한다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="사용자 ID(UUID)")
    username: str = Field(..., description="사용자명")
    email: str = Field(..., description="이메일")
    is_active: bool = Field(..., description="활성 여부")


class TokenResponse(BaseModel):
    """토큰 응답(OAuth2 bearer)."""

    access_token: str = Field(..., description="API 호출에 사용하는 Access Token")
    refresh_token: str = Field(..., description="Access Token 재발급에 사용하는 Refresh Token")
    token_type: str = Field(default="bearer", description="토큰 타입 — 항상 `bearer`")


class RefreshRequest(BaseModel):
    """토큰 재발급 요청."""

    refresh_token: str = Field(..., description="유효한 Refresh Token")
