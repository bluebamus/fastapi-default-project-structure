"""인가 — 인증 주체 ``Principal`` 과 소유권 규칙 ``OwnershipPolicy`` (service-hardening ADR-017·018).

``Principal`` 은 검증된 access 토큰의 claim 으로만 만든다(DB 조회 없음). 기능은 사용자 모델을
import 하지 않고 이 값 객체 하나에만 기대므로, 기능끼리 import 하지 않는 계층 규칙(C-2)이 지켜진다.

인가는 슈퍼유저/일반 2단계다. 수정·삭제 권한은 ``OwnershipPolicy`` 한 곳에서 정한다 — 소유자
본인이거나 슈퍼유저면 허용, 아니면 403. 소유자가 없는 행(``owner_id`` 가 NULL — 인가 도입 전에
만든 게시글)은 슈퍼유저만 고칠 수 있다(residual-risk R-006).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exception import ForbiddenException


@dataclass(frozen=True, slots=True)
class Principal:
    """인증된 요청의 주체 — access 토큰의 ``sub``·``username``·``su``.

    ``is_superuser`` 는 토큰 발급 시점의 값이다. 권한을 회수해도 이미 발급된 access 토큰은
    만료(기본 15분)까지 이전 권한을 가진다(residual-risk R-002).
    """

    id: str
    username: str
    is_superuser: bool


class OwnershipPolicy:
    """소유자 또는 슈퍼유저만 리소스를 바꿀 수 있다."""

    def ensure_can_modify(self, owner_id: str | None, principal: Principal) -> None:
        """권한이 없으면 ``ForbiddenException``(403).

        Args:
            owner_id: 리소스 소유자의 사용자 ID. ``None`` 이면 소유자가 없는 행이다.
            principal: 요청 주체.
        """
        if principal.is_superuser:
            return
        if owner_id is None or owner_id != principal.id:
            raise ForbiddenException()
