"""``TokenService`` — claim 구성과 검증 규칙 (service-hardening ADR-014).

검증 실패는 무엇이든 ``InvalidTokenException``(401) 하나다. 여기서는 각 거부 사유를 따로 만들어
그 하나하나가 실제로 거부되는지 본다 — 검사 하나가 빠져도 다른 테스트가 통과해 버리지 않게.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core.security.tokens import (
    ACCESS_REQUIRED_CLAIMS,
    REQUIRED_CLAIMS,
    InvalidTokenException,
    TokenService,
    TokenType,
)
from config import JWTSettings

ACCESS_KEY = "a" * 64  # HS512 권장 최소 길이(64바이트) — 경고 없이 서명한다
REFRESH_KEY = "r" * 64


def _settings(**overrides) -> JWTSettings:
    values = {
        "ACCESS_TOKEN_SECRET_KEY": ACCESS_KEY,
        "REFRESH_TOKEN_SECRET_KEY": REFRESH_KEY,
        "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
        "REFRESH_TOKEN_EXPIRE_DAYS": 7,
        "JWT_ALGORITHM": "HS256",
        "JWT_ISSUER": "test-issuer",
        "JWT_AUDIENCE": "test-audience",
        "JWT_LEEWAY_SECONDS": 10,
    }
    values.update(overrides)
    return JWTSettings(**values)


@pytest.fixture
def tokens() -> TokenService:
    return TokenService(_settings())


def _claims(**overrides) -> dict:
    now = datetime.now(UTC)
    claims = {
        "sub": "user-1",
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": "j" * 32,
        "iss": "test-issuer",
        "aud": "test-audience",
        "username": "alice",
        "su": False,
    }
    claims.update(overrides)
    return claims


def _sign(claims: dict, key: str = ACCESS_KEY, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key, algorithm=algorithm)


# =============================================================================
# 발급
# =============================================================================
def test_access_token_carries_standard_claims_and_username(tokens):
    issued = tokens.issue_access("user-1", "alice", False)

    claims = tokens.decode(issued.token, TokenType.ACCESS)

    assert claims["sub"] == "user-1"
    assert claims["type"] == "access"
    assert claims["username"] == "alice"
    assert claims["su"] is False
    assert claims["iss"] == "test-issuer"
    assert claims["aud"] == "test-audience"
    assert claims["jti"] == issued.jti and len(issued.jti) == 32
    assert claims["nbf"] == claims["iat"]
    assert claims["exp"] - claims["iat"] == 15 * 60 == issued.ttl_seconds


def test_refresh_token_carries_family(tokens):
    issued = tokens.issue_refresh("user-1", "fam-1")

    claims = tokens.decode(issued.token, TokenType.REFRESH)

    assert claims["fam"] == "fam-1"
    assert claims["type"] == "refresh"
    assert claims["exp"] - claims["iat"] == 7 * 86400 == tokens.refresh_ttl_seconds


def test_every_token_gets_a_fresh_jti(tokens):
    assert tokens.issue_access("u", "n", False).jti != tokens.issue_access("u", "n", False).jti


# =============================================================================
# 거부
# =============================================================================
def test_expired_token_is_rejected(tokens):
    expired = _sign(_claims(exp=datetime.now(UTC) - timedelta(seconds=30)))

    with pytest.raises(InvalidTokenException):
        tokens.decode(expired, TokenType.ACCESS)


def test_leeway_tolerates_small_clock_skew(tokens):
    just_expired = _sign(_claims(exp=datetime.now(UTC) - timedelta(seconds=3)))

    assert tokens.decode(just_expired, TokenType.ACCESS)["sub"] == "user-1"


def test_not_yet_valid_token_is_rejected(tokens):
    future = _sign(_claims(nbf=datetime.now(UTC) + timedelta(minutes=1)))

    with pytest.raises(InvalidTokenException):
        tokens.decode(future, TokenType.ACCESS)


@pytest.mark.parametrize(
    "overrides",
    [{"aud": "other-audience"}, {"iss": "other-issuer"}],
    ids=["audience", "issuer"],
)
def test_foreign_issuer_or_audience_is_rejected(tokens, overrides):
    with pytest.raises(InvalidTokenException):
        tokens.decode(_sign(_claims(**overrides)), TokenType.ACCESS)


def test_superuser_flag_is_carried_in_su_claim(tokens):
    """인가는 토큰의 ``su`` 로 정해진다 — DB 조회 없이 Principal 을 만든다(service-hardening ADR-017)."""
    claims = tokens.decode(tokens.issue_access("user-1", "root", True).token, TokenType.ACCESS)

    assert claims["su"] is True


def test_access_requires_username_and_su_but_refresh_does_not():
    assert set(ACCESS_REQUIRED_CLAIMS) - set(REQUIRED_CLAIMS) == {"username", "su"}


@pytest.mark.parametrize("missing", ACCESS_REQUIRED_CLAIMS)
def test_token_missing_a_required_claim_is_rejected(tokens, missing):
    claims = _claims()
    del claims[missing]

    with pytest.raises(InvalidTokenException):
        tokens.decode(_sign(claims), TokenType.ACCESS)


def test_access_token_is_not_accepted_as_refresh(tokens):
    access = tokens.issue_access("user-1", "alice", False).token

    with pytest.raises(InvalidTokenException):
        tokens.decode(access, TokenType.REFRESH)


def test_type_claim_is_checked_even_with_the_right_key(tokens):
    """키가 맞아도 ``type`` 이 다르면 거부한다 — 키를 하나로 합치는 설정 실수에 대한 두 번째 벽."""
    mislabeled = _sign(_claims(type="refresh"), key=ACCESS_KEY)

    with pytest.raises(InvalidTokenException):
        tokens.decode(mislabeled, TokenType.ACCESS)


@pytest.mark.parametrize("algorithm", ["HS512", "none"])
def test_algorithm_other_than_configured_is_rejected(tokens, algorithm):
    key = None if algorithm == "none" else ACCESS_KEY
    forged = jwt.encode(_claims(), key, algorithm=algorithm)

    with pytest.raises(InvalidTokenException):
        tokens.decode(forged, TokenType.ACCESS)


def test_tampered_signature_is_rejected(tokens):
    header, payload, _ = tokens.issue_access("user-1", "alice", False).token.split(".")
    other = _sign(_claims(), key="x" * 64).split(".")[2]

    with pytest.raises(InvalidTokenException):
        tokens.decode(f"{header}.{payload}.{other}", TokenType.ACCESS)


def test_rejection_is_a_401_with_a_single_error_code(tokens):
    with pytest.raises(InvalidTokenException) as exc_info:
        tokens.decode("garbage", TokenType.ACCESS)

    assert exc_info.value.status_code == 401
    assert exc_info.value.error_code == "AUTH_INVALID_TOKEN"


# =============================================================================
# 설정
# =============================================================================
@pytest.mark.parametrize("algorithm", ["RS256", "none", "HS1"])
def test_only_hmac_algorithms_are_configurable(algorithm):
    with pytest.raises(ValidationError):
        _settings(JWT_ALGORITHM=algorithm)


def test_access_token_default_lifetime_is_15_minutes():
    assert JWTSettings.model_fields["ACCESS_TOKEN_EXPIRE_MINUTES"].default == 15
