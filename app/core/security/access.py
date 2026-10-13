"""뷰 단위 접근 수준 선언과 기본 거부 정책 (access-policy ADR-001~003).

모든 API 뷰는 경로 데코레이터의 ``dependencies=[...]`` 에 접근 수준을 하나 선언한다::

    @router.get("/posts", dependencies=[Public])                # 인증 없는 조회
    @router.post("/login", dependencies=[PublicWrite])          # 인증 없는 쓰기(명시적으로 연다)
    @router.post("/posts", dependencies=[LoginRequired])        # 로그인(401)
    @router.delete("/x/{id}", dependencies=[SuperuserRequired]) # 슈퍼유저(401/403)

사용자 정보가 필요한 뷰는 데코레이터 대신 인자 ``principal: CurrentPrincipal`` /
``SuperuserPrincipal`` 로 받아도 같은 선언으로 인정한다(둘 다 적을 필요 없다).

함수를 감싸는 데코레이터(Django 식 ``@login_required``)는 만들지 않는다 — FastAPI 는 핸들러
시그니처로 의존성 주입·검증·OpenAPI 를 만들므로, 감싸면 그 정보가 가려진다.

데코레이터만으로는 "선언을 빠뜨린 뷰"가 열린 채 배포된다. 그래서 ``AccessPolicyGuard`` 가 앱
조립 직후 모든 라우트를 훑어 선언이 없거나 모순된 뷰가 있으면 **기동을 멈춘다**(기본 거부).
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

from app.core.security.dependencies import get_current_principal, require_superuser


async def public() -> None:
    """표식: 인증 없는 조회. 아무것도 하지 않는다(async 라 스레드풀도 타지 않는다)."""


async def public_write() -> None:
    """표식: 인증 없는 쓰기를 의도적으로 연다(가입·로그인·refresh·logout)."""


Public = Depends(public)
PublicWrite = Depends(public_write)
LoginRequired = Depends(get_current_principal)
SuperuserRequired = Depends(require_superuser)


class AccessLevel(StrEnum):
    PUBLIC = "Public"
    PUBLIC_WRITE = "PublicWrite"
    LOGIN = "LoginRequired"
    SUPERUSER = "SuperuserRequired"


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class AccessPolicyError(RuntimeError):
    """접근 수준 선언 위반 — 기동을 멈춘다(설정 검사와 같은 ``RuntimeError`` 계열)."""


class AccessPolicyGuard:
    """앱이 서빙하는 모든 ``APIRoute`` 가 접근 수준을 정확히 하나 선언했는지 검사한다.

    대상은 중첩 include 를 펼친 모든 ``APIRoute``(``include_in_schema=False`` 포함)다.
    FastAPI 가 붙이는 문서 경로(Starlette ``Route``)와 ``Mount``(``/admin`` — 자체 세션 인증)는
    ``APIRoute`` 가 아니므로 빠진다.
    """

    def routes(self, app: FastAPI) -> Iterator[tuple[str, Any]]:
        """``("GET /api/v1/blog/posts", 라우트 문맥)`` 을 낸다. 문맥은 전체 경로·라우터 단위
        의존성까지 합친 유효 라우트다(FastAPI 0.141 의 ``_IncludedRouter`` 를 펼친다)."""
        for context in iter_route_contexts(app.routes):
            if isinstance(context.original_route, APIRoute):
                methods = ",".join(sorted(context.methods or ()))
                yield f"{methods} {context.path}", context

    def levels(self, dependant: Dependant) -> set[AccessLevel]:
        """의존성 트리에 선언된 접근 수준. 슈퍼유저는 내부에서 로그인을 쓰므로 슈퍼유저로 접는다."""
        calls = set()
        stack = [dependant]
        while stack:
            node = stack.pop()
            calls.add(node.call)
            stack.extend(node.dependencies)
        found = {
            level
            for call, level in (
                (public, AccessLevel.PUBLIC),
                (public_write, AccessLevel.PUBLIC_WRITE),
                (require_superuser, AccessLevel.SUPERUSER),
                (get_current_principal, AccessLevel.LOGIN),
            )
            if call in calls
        }
        if AccessLevel.SUPERUSER in found:
            found.discard(AccessLevel.LOGIN)
        return found

    def violations(self, app: FastAPI) -> list[str]:
        problems = []
        for label, context in self.routes(app):
            levels = self.levels(context.dependant)
            methods = set(context.methods or ())
            if not levels:
                problems.append(f"{label}: 접근 수준 선언 없음")
            elif len(levels) > 1:
                names = ", ".join(sorted(levels))
                problems.append(f"{label}: 접근 수준을 둘 이상 선언함({names})")
            elif AccessLevel.PUBLIC in levels and methods - SAFE_METHODS:
                problems.append(f"{label}: 쓰기 메서드에 Public — 인증 없는 쓰기는 PublicWrite")
            elif AccessLevel.PUBLIC_WRITE in levels and methods & SAFE_METHODS:
                problems.append(f"{label}: 안전한 메서드에 PublicWrite — 조회는 Public")
        return problems

    def verify(self, app: FastAPI) -> None:
        problems = self.violations(app)
        if problems:
            raise AccessPolicyError(
                "접근 수준 선언 위반으로 기동을 멈춥니다 — 뷰의 dependencies=[...] 에 "
                "Public·PublicWrite·LoginRequired·SuperuserRequired 중 하나를 선언하세요 "
                "(app/core/security/access.py):\n  " + "\n  ".join(problems)
            )
