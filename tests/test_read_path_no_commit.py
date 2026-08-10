"""조회 엔드포인트가 커밋 의존성을 쓰지 않는지 전 도메인 대조 (계획서 P4-1).

도메인마다 in-memory DB 픽스처로 커밋 횟수를 세는 방식은 도메인 수만큼 픽스처가
복제된다. 여기서는 대신 **라우트의 의존성 트리를 직접 검사**해서 5개 도메인을 한
테스트로 덮는다. 새 도메인이 추가돼도 자동으로 검사 대상이 된다.

지키려는 규칙:
    1. 커밋하는 의존성(`get_<name>_service`)은 쓰기 메서드에서만 쓴다.
    2. 조회 라우트는 쓰기 세션(`get_session`)을 쓰지 않는다.

조회에 커밋 의존성을 재사용하면 조회마다 불필요한 COMMIT 왕복이 생기고, 인증 등
다른 의존성과 함께 쓸 때 한 세션에 커밋 주체가 둘이 되어 부분 저장 위험이 생긴다.

2번이 따로 필요한 이유: 커밋만 안 하면 될 것 같지만, 쓰기 세션을 그대로 쓰면
조회가 여전히 writer 로 간다. `DB_ROUTER_ENABLED` 를 켜도 replica 로 분산되지
않아 read/write 분리가 무력해진다(P4-3 에서 auth 가 정확히 이 상태였다).
"""

from fastapi.routing import APIRoute

from app.core.db.session import get_session
from app.domains.auth.dependencies.auth_dependencies import get_auth_service
from app.domains.blog.dependencies.blog_dependencies import get_blog_service
from app.domains.reply.dependencies.reply_dependencies import get_reply_service
from app.domains.sns.dependencies.sns_dependencies import get_sns_service
from app.domains.user.dependencies.user_dependencies import get_user_service
from main import app

# yield 이후 session.commit() 을 호출하는 의존성 전부.
_COMMITTING_DEPENDENCIES = {
    get_auth_service,
    get_blog_service,
    get_reply_service,
    get_sns_service,
    get_user_service,
}

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 조회인데도 writer 세션이 반드시 필요한 라우트가 생기면 여기에 이유와 함께 적는다
# (예: 복제 지연을 허용할 수 없는 read-after-write 조회).
_WRITER_SESSION_BY_DESIGN: dict[str, str] = {}


def _dependency_calls(route: APIRoute) -> set:
    """라우트의 의존성 트리에 등장하는 모든 호출 대상을 모은다."""
    calls = set()
    stack = [route.dependant]
    while stack:
        dependant = stack.pop()
        if dependant.call is not None:
            calls.add(dependant.call)
        stack.extend(dependant.dependencies)
    return calls


def _api_routes() -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api")]


def test_read_routes_do_not_use_committing_dependencies():
    """GET 전용 라우트는 커밋 의존성을 쓰지 않는다."""
    offenders = []
    for route in _api_routes():
        if route.methods and route.methods <= {"GET", "HEAD", "OPTIONS"}:
            used = _dependency_calls(route) & _COMMITTING_DEPENDENCIES
            if used:
                offenders.append((route.path, sorted(d.__name__ for d in used)))

    assert not offenders, (
        f"조회 라우트가 커밋 의존성을 사용함: {offenders}. "
        "get_<name>_service_readonly 로 바꿀 것."
    )


def test_read_routes_do_not_use_writer_session():
    """GET 전용 라우트는 쓰기 세션을 쓰지 않는다.

    커밋을 안 하더라도 writer 세션을 잡으면 조회가 replica 로 분산되지 않는다.
    """
    offenders = [
        route.path
        for route in _api_routes()
        if route.methods
        and route.methods <= {"GET", "HEAD", "OPTIONS"}
        and get_session in _dependency_calls(route)
        and route.path not in _WRITER_SESSION_BY_DESIGN
    ]

    assert not offenders, (
        f"조회 라우트가 쓰기 세션(get_session)을 사용함: {sorted(offenders)}. "
        "get_read_session 으로 바꾸거나, 복제 지연을 허용할 수 없는 조회라면 "
        "_WRITER_SESSION_BY_DESIGN 에 이유와 함께 추가할 것."
    )


def test_write_routes_still_commit():
    """쓰기 라우트는 반드시 커밋 의존성을 갖는다.

    P4-1 에서 읽기를 분리하다가 쓰기까지 read-only 로 바꿔버리면 데이터가 저장되지
    않는다. 반대 방향 사고를 막는 짝 테스트다.
    """
    missing = [
        route.path
        for route in _api_routes()
        if route.methods
        and route.methods & _WRITE_METHODS
        and not (_dependency_calls(route) & _COMMITTING_DEPENDENCIES)
    ]

    assert not missing, f"쓰기 라우트에 커밋 의존성이 없다: {missing}"


def test_coverage_is_not_vacuous():
    """검사 대상이 실제로 존재하는지 확인한다.

    라우팅이 바뀌어 _api_routes() 가 비면 위 두 테스트는 조용히 통과한다.
    """
    routes = _api_routes()
    read_routes = [r for r in routes if r.methods and r.methods <= {"GET", "HEAD", "OPTIONS"}]
    write_routes = [r for r in routes if r.methods and r.methods & _WRITE_METHODS]

    assert len(read_routes) >= 13, f"조회 라우트가 {len(read_routes)}개뿐 — 검사가 비었을 수 있다"
    assert write_routes, "쓰기 라우트를 하나도 찾지 못했다"
