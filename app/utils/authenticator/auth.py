"""인증 유틸리티.

비밀번호 해시(bcrypt)와 JWT access/refresh 토큰 생성·검증을 제공하는 순수 함수 모음.
프레임워크에 독립적이며, auth 도메인 서비스와 `get_current_user` 의존성이 사용한다.

주의: bcrypt 는 72바이트를 초과하는 비밀번호를 거부하므로 입력을 72바이트로 잘라서 사용한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from config import jwt_settings

_BCRYPT_MAX_BYTES = 72

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def _pw_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """비밀번호를 bcrypt 로 해시한다."""
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """평문 비밀번호가 해시와 일치하는지 검증한다(불일치·오류 시 False)."""
    try:
        return bcrypt.checkpw(_pw_bytes(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _create_token(
    subject: str,
    token_type: str,
    secret: str,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm=jwt_settings.JWT_ALGORITHM)


def create_access_token(
    subject: str,
    *,
    expires_delta: timedelta | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Access Token 을 생성한다(기본 만료: 설정의 ACCESS_TOKEN_EXPIRE_MINUTES)."""
    delta = expires_delta or timedelta(minutes=jwt_settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(
        subject, ACCESS_TOKEN_TYPE, jwt_settings.ACCESS_TOKEN_SECRET_KEY, delta, extra
    )


def create_refresh_token(
    subject: str,
    *,
    expires_delta: timedelta | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Refresh Token 을 생성한다(기본 만료: 설정의 REFRESH_TOKEN_EXPIRE_DAYS)."""
    delta = expires_delta or timedelta(days=jwt_settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return _create_token(
        subject, REFRESH_TOKEN_TYPE, jwt_settings.REFRESH_TOKEN_SECRET_KEY, delta, extra
    )


def decode_token(token: str, *, token_type: str = ACCESS_TOKEN_TYPE) -> dict[str, Any]:
    """토큰을 검증·디코드한다.

    만료·서명 오류·타입 불일치 시 `jwt.InvalidTokenError`(하위 포함)를 발생시킨다.
    """
    secret = (
        jwt_settings.ACCESS_TOKEN_SECRET_KEY
        if token_type == ACCESS_TOKEN_TYPE
        else jwt_settings.REFRESH_TOKEN_SECRET_KEY
    )
    payload = jwt.decode(token, secret, algorithms=[jwt_settings.JWT_ALGORITHM])
    if payload.get("type") != token_type:
        raise jwt.InvalidTokenError(f"expected {token_type} token, got {payload.get('type')!r}")
    return payload
