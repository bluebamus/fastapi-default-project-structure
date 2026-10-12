"""비밀번호 해시 — ``PasswordHasher`` (service-hardening ADR-013·ADR-026).

새 해시는 Argon2id(pwdlib). 이전 버전이 저장한 bcrypt 해시(``$2`` 접두사)는 그때 규칙
그대로(UTF-8 72바이트 절단) 검증하고, 맞으면 새 Argon2 해시를 돌려준다 — 호출자가 저장하면
로그인할 때마다 한 명씩 옮겨 간다(평문이 없어 일괄 재해시는 불가능하다).

Argon2 는 일부러 느린(수십 ms, 64MiB) 연산이라 이벤트 루프를 막지 않도록 스레드에서 돌린다.
사용자가 없거나 비밀번호가 없는 계정에도 더미 해시로 같은 비용을 치러, 응답 시간으로 사용자명
존재를 알아내지 못하게 한다.
"""

from __future__ import annotations

import asyncio

import bcrypt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

_LEGACY_BCRYPT_PREFIX = "$2"
_LEGACY_BCRYPT_MAX_BYTES = 72


class PasswordHasher:
    """비밀번호 해시·검증·점진 이전. 프로세스에 하나만 둔다(``get_password_hasher``)."""

    def __init__(self) -> None:
        self._hash = PasswordHash((Argon2Hasher(),))
        self._dummy_hash = self._hash.hash("constant-time-dummy-password")

    async def hash(self, password: str) -> str:
        """Argon2id 해시를 만든다."""
        return await asyncio.to_thread(self._hash.hash, password)

    async def verify_and_update(self, password: str, stored: str | None) -> tuple[bool, str | None]:
        """비밀번호를 검증한다.

        Args:
            password: 입력 평문
            stored: 저장된 해시. ``None`` 이면(사용자 없음·비밀번호 미설정) 더미 해시로 같은
                비용을 치르고 실패를 돌려준다.

        Returns:
            ``(일치 여부, 새 해시 또는 None)``. 새 해시가 있으면 호출자가 저장해야 한다 —
            레거시 bcrypt 이거나 Argon2 파라미터가 바뀐 경우다.
        """
        if stored is None:
            await asyncio.to_thread(self._hash.verify, password, self._dummy_hash)
            return False, None
        return await asyncio.to_thread(self._verify_and_update, password, stored)

    def _verify_and_update(self, password: str, stored: str) -> tuple[bool, str | None]:
        if stored.startswith(_LEGACY_BCRYPT_PREFIX):
            if not self._verify_legacy_bcrypt(password, stored):
                return False, None
            return True, self._hash.hash(password)
        try:
            return self._hash.verify_and_update(password, stored)
        except UnknownHashError:
            return False, None

    @staticmethod
    def _verify_legacy_bcrypt(password: str, stored: str) -> bool:
        # 이전 버전은 bcrypt 의 72바이트 한계 때문에 입력을 잘라 해시했다. 같은 규칙으로 잘라야
        # 72바이트를 넘는 기존 비밀번호가 맞는다. 새 해시(Argon2)에는 절단이 없다.
        candidate = password.encode("utf-8")[:_LEGACY_BCRYPT_MAX_BYTES]
        try:
            return bcrypt.checkpw(candidate, stored.encode("utf-8"))
        except ValueError:
            return False
