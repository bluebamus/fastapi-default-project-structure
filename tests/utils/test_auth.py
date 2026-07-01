"""app/utils/authenticator/auth.py 단위 테스트 (bcrypt 해시 + JWT 토큰)."""
from datetime import timedelta

import jwt
import pytest

from app.utils.authenticator.auth import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("s3cret-pw")
    assert hashed != "s3cret-pw"
    assert verify_password("s3cret-pw", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_password_over_72_bytes_does_not_crash():
    long_pw = "a" * 200
    hashed = hash_password(long_pw)
    assert verify_password(long_pw, hashed) is True


def test_access_token_roundtrip():
    token = create_access_token("user-123")
    payload = decode_token(token, token_type=ACCESS_TOKEN_TYPE)
    assert payload["sub"] == "user-123"
    assert payload["type"] == ACCESS_TOKEN_TYPE


def test_refresh_token_roundtrip():
    token = create_refresh_token("user-123")
    payload = decode_token(token, token_type=REFRESH_TOKEN_TYPE)
    assert payload["sub"] == "user-123"
    assert payload["type"] == REFRESH_TOKEN_TYPE


def test_access_token_cannot_be_decoded_as_refresh():
    token = create_access_token("user-123")
    # 서명 키가 달라 서명 검증에서 먼저 실패한다.
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, token_type=REFRESH_TOKEN_TYPE)


def test_expired_token_raises():
    token = create_access_token("user-123", expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token, token_type=ACCESS_TOKEN_TYPE)


def test_tampered_token_raises():
    token = create_access_token("user-123")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token + "tamper", token_type=ACCESS_TOKEN_TYPE)


def test_extra_claims_included():
    token = create_access_token("user-123", extra={"role": "admin"})
    payload = decode_token(token)
    assert payload["role"] == "admin"
