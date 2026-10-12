"""``PasswordHasher`` — Argon2 해시·검증, 레거시 bcrypt 점진 이전 (service-hardening ADR-013)."""

import bcrypt
import pytest

from app.features.auth.services.password_hasher import PasswordHasher


@pytest.fixture(scope="module")
def hasher() -> PasswordHasher:
    return PasswordHasher()


def _legacy_bcrypt(password: str) -> str:
    """이전 버전의 저장 규칙 — UTF-8 72바이트로 잘라 bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=4)).decode()


async def test_hash_is_argon2id_and_verifies(hasher):
    hashed = await hasher.hash("s3cret-password")

    assert hashed.startswith("$argon2id$")
    assert await hasher.verify_and_update("s3cret-password", hashed) == (True, None)
    assert await hasher.verify_and_update("wrong-password", hashed) == (False, None)


async def test_long_password_is_not_truncated(hasher):
    """Argon2 에는 72바이트 한계가 없다 — 앞 72바이트만 같은 다른 비밀번호는 틀려야 한다."""
    base = "x" * 72
    hashed = await hasher.hash(base + "-tail-one")

    assert (await hasher.verify_and_update(base + "-tail-two", hashed))[0] is False


async def test_legacy_bcrypt_hash_verifies_and_returns_argon2_rehash(hasher):
    password = "옛날-비밀번호-" + "z" * 80  # 72바이트 초과 — 이전 절단 규칙까지 맞아야 한다
    ok, new_hash = await hasher.verify_and_update(password, _legacy_bcrypt(password))

    assert ok is True
    assert new_hash is not None and new_hash.startswith("$argon2id$")
    assert await hasher.verify_and_update(password, new_hash) == (True, None)


async def test_legacy_bcrypt_with_wrong_password_returns_no_rehash(hasher):
    assert await hasher.verify_and_update("wrong", _legacy_bcrypt("right-password")) == (
        False,
        None,
    )


@pytest.mark.parametrize("stored", [None, "not-a-hash", "$2b$broken"])
async def test_missing_or_unknown_hash_fails_without_error(hasher, stored):
    assert await hasher.verify_and_update("anything", stored) == (False, None)
