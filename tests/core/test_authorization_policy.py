"""``OwnershipPolicy`` · ``get_current_principal`` · ``require_superuser`` 단위 규칙 (service-hardening ADR-017·018)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.exception import ForbiddenException
from app.core.security.authorization import OwnershipPolicy, Principal
from app.core.security.dependencies import (
    get_current_principal,
    get_token_service,
    require_superuser,
)
from app.core.security.tokens import InvalidTokenException

OWNER = Principal(id="u-1", username="owner", is_superuser=False)
OTHER = Principal(id="u-2", username="other", is_superuser=False)
ROOT = Principal(id="u-3", username="root", is_superuser=True)


@pytest.fixture
def policy() -> OwnershipPolicy:
    return OwnershipPolicy()


def test_owner_may_modify(policy):
    policy.ensure_can_modify("u-1", OWNER)


def test_other_user_is_forbidden(policy):
    with pytest.raises(ForbiddenException):
        policy.ensure_can_modify("u-1", OTHER)


def test_superuser_may_modify_anything_including_ownerless_rows(policy):
    policy.ensure_can_modify("u-1", ROOT)
    policy.ensure_can_modify(None, ROOT)


def test_ownerless_row_is_forbidden_for_normal_users(policy):
    with pytest.raises(ForbiddenException):
        policy.ensure_can_modify(None, OWNER)


def test_principal_is_immutable():
    with pytest.raises(AttributeError):
        OWNER.is_superuser = True  # type: ignore[misc]


async def test_require_superuser():
    assert await require_superuser(ROOT) is ROOT
    with pytest.raises(ForbiddenException):
        await require_superuser(OWNER)


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace())


async def test_principal_is_built_from_claims_and_recorded_on_request_state():
    tokens = get_token_service()
    request = _request()

    principal = await get_current_principal(
        request,  # type: ignore[arg-type]
        tokens.issue_access("u-9", "nine", True).token,
        tokens,
    )

    assert principal == Principal(id="u-9", username="nine", is_superuser=True)
    assert request.state.user_id == "u-9"  # 접속 로그가 응답 뒤에 읽는다


async def test_refresh_token_is_not_a_principal():
    tokens = get_token_service()
    request = _request()

    with pytest.raises(InvalidTokenException):
        await get_current_principal(
            request,  # type: ignore[arg-type]
            tokens.issue_refresh("u-9", "fam").token,
            tokens,
        )
    assert not hasattr(request.state, "user_id")
