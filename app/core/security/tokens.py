"""JWT 발급·검증 — ``TokenService`` (service-hardening ADR-014·ADR-025).

claims: ``sub, type, iat, nbf, exp, jti, iss, aud`` + access 는 ``username``, refresh 는 ``fam``
(회전 family). 검증은 알고리즘을 설정 하나로 고정하고, ``iss``·``aud`` 일치와 필수 claim 존재를
요구하며, ``type`` 이 기대와 다르면 거부한다. access 와 refresh 는 서명 키도 다르다 — 종류를
바꿔 끼우면 서명 단계에서 먼저 실패하고, ``type`` 검사가 두 번째 벽이다.

모든 검증 실패는 ``InvalidTokenException``(401) 하나로 모은다. 어느 검사에서 걸렸는지는
응답에 싣지 않는다(공격자에게 힌트가 된다).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, NamedTuple

import jwt

from app.core.exception import UnauthorizedException
from config import JWTSettings

# decode 가 존재를 요구하는 claim. 하나라도 없으면 위조·다른 발급자의 토큰으로 본다.
REQUIRED_CLAIMS = ["exp", "iat", "nbf", "sub", "jti", "iss", "aud", "type"]


class TokenType(StrEnum):
    """``type`` claim 값."""

    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenException(UnauthorizedException):
    """유효하지 않은·만료된·재사용된 토큰 (401)."""

    error_code = "AUTH_INVALID_TOKEN"
    message = "유효하지 않은 인증 토큰입니다."


class IssuedToken(NamedTuple):
    """발급 결과 — 토큰 문자열과 회전 저장소·응답이 쓰는 메타데이터."""

    token: str
    jti: str
    ttl_seconds: int


class TokenService:
    """access/refresh 토큰을 발급하고 검증한다. 설정은 생성자로 받는다."""

    def __init__(self, settings: JWTSettings) -> None:
        self._settings = settings
        self._keys = {
            TokenType.ACCESS: settings.ACCESS_TOKEN_SECRET_KEY,
            TokenType.REFRESH: settings.REFRESH_TOKEN_SECRET_KEY,
        }
        self._ttls = {
            TokenType.ACCESS: settings.access_token_ttl_seconds,
            TokenType.REFRESH: settings.refresh_token_ttl_seconds,
        }

    @property
    def refresh_ttl_seconds(self) -> int:
        """refresh 토큰 유효 시간(초) — 회전 기록·폐기 표시가 같은 TTL 을 쓴다."""
        return self._ttls[TokenType.REFRESH]

    def issue_access(self, sub: str, username: str) -> IssuedToken:
        """access 토큰을 발급한다."""
        return self._issue(TokenType.ACCESS, sub, {"username": username})

    def issue_refresh(self, sub: str, family: str) -> IssuedToken:
        """refresh 토큰을 발급한다. ``family`` 는 회전으로 이어지는 토큰 묶음의 ID 다."""
        return self._issue(TokenType.REFRESH, sub, {"fam": family})

    def _issue(self, token_type: TokenType, sub: str, extra: dict[str, Any]) -> IssuedToken:
        now = datetime.now(UTC)
        ttl = self._ttls[token_type]
        jti = uuid.uuid4().hex
        payload: dict[str, Any] = {
            **extra,
            "sub": sub,
            "type": token_type.value,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=ttl),
            "jti": jti,
            "iss": self._settings.JWT_ISSUER,
            "aud": self._settings.JWT_AUDIENCE,
        }
        token = jwt.encode(payload, self._keys[token_type], algorithm=self._settings.JWT_ALGORITHM)
        return IssuedToken(token=token, jti=jti, ttl_seconds=ttl)

    def decode(self, token: str, expected_type: TokenType) -> dict[str, Any]:
        """서명·시각·발급자·대상·필수 claim·종류를 검증하고 claims 를 돌려준다.

        Raises:
            InvalidTokenException: 어느 검증이든 실패하면(401).
        """
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self._keys[expected_type],
                algorithms=[self._settings.JWT_ALGORITHM],
                audience=self._settings.JWT_AUDIENCE,
                issuer=self._settings.JWT_ISSUER,
                leeway=self._settings.JWT_LEEWAY_SECONDS,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenException() from exc
        if claims["type"] != expected_type.value:
            raise InvalidTokenException()
        return claims
