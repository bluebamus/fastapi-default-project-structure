"""이메일 형식 검증 회귀 테스트.

회원가입(auth.RegisterRequest)과 사용자 생성(user.UserCreate)이 동일한 이메일 규칙
(app.utils.validators.EMAIL_PATTERN)으로 잘못된 형식을 거부하는지 확인한다.
"""

import pytest
from pydantic import ValidationError

from app.domains.auth.schemas.auth_schema import RegisterRequest
from app.domains.user.schemas.user_schema import UserCreate

_INVALID_EMAILS = [
    "notanemail",
    "no-at-sign.com",
    "missing@domain",
    "a@b@c.com",
    "with space@x.com",
]


@pytest.mark.parametrize("bad_email", _INVALID_EMAILS)
def test_register_rejects_invalid_email(bad_email):
    """회원가입은 잘못된 이메일 형식을 거부한다(422 유발)."""
    with pytest.raises(ValidationError):
        RegisterRequest(username="alice", email=bad_email, password="password123")


@pytest.mark.parametrize("bad_email", _INVALID_EMAILS)
def test_user_create_rejects_invalid_email(bad_email):
    """사용자 생성도 동일 규칙으로 잘못된 이메일을 거부한다."""
    with pytest.raises(ValidationError):
        UserCreate(username="alice", email=bad_email)


def test_valid_email_is_accepted():
    """정상 이메일은 두 스키마 모두 통과한다."""
    reg = RegisterRequest(username="alice", email="alice@example.com", password="password123")
    assert reg.email == "alice@example.com"
    user = UserCreate(username="bob", email="bob@example.co.kr")
    assert user.email == "bob@example.co.kr"
