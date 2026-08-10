"""트랜잭션 배선을 라우트 단위로 대조한다 (계획서 P4-1 / P4-3 / P1-3).

도메인마다 in-memory DB 픽스처로 커밋 횟수를 세는 방식은 도메인 수만큼 픽스처가
복제된다. 여기서는 대신 **라우트의 의존성 트리와 핸들러 본문을 직접 검사**해서
전 도메인을 한 파일로 덮는다. 새 도메인이 추가돼도 자동으로 검사 대상이 된다.

지키려는 규칙:
    1. 조회 라우트는 쓰기용 서비스 의존성을 쓰지 않는다      (P4-1)
    2. 조회 라우트는 쓰기 세션(`get_session`)을 쓰지 않는다   (P4-3)
    3. 쓰기 라우트는 쓰기용 서비스 의존성을 쓴다             (P4-1 역방향)
    4. 쓰기 라우트는 핸들러 본문에서 커밋한다                (P1-3)

2번이 따로 필요한 이유: 커밋만 안 하면 될 것 같지만, 쓰기 세션을 그대로 쓰면
조회가 여전히 writer 로 간다. `DB_ROUTER_ENABLED` 를 켜도 replica 로 분산되지
않아 read/write 분리가 무력해진다(P4-3 에서 auth 가 정확히 이 상태였다).

4번이 따로 필요한 이유: 커밋은 의존성 teardown 이 아니라 핸들러 본문에서 해야
한다. FastAPI 상위 버전은 yield dependency 의 종료 코드를 **응답 전송 후에**
실행하므로, teardown 에서 커밋하면 실패해도 클라이언트는 201 을 받는다(P1-3).
"""

import inspect

from fastapi.routing import APIRoute

from app.core.db.session import get_session
from app.domains.auth.dependencies.auth_dependencies import get_auth_service
from app.domains.blog.dependencies.blog_dependencies import get_blog_service
from app.domains.reply.dependencies.reply_dependencies import get_reply_service
from app.domains.sns.dependencies.sns_dependencies import get_sns_service
from app.domains.user.dependencies.user_dependencies import get_user_service
from main import app

# 쓰기 세션(get_session)으로 서비스를 구성하는 의존성 전부.
_WRITE_DEPENDENCIES = {
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

# 쓰기 메서드지만 실제로 DB에 쓰지 않는 라우트. 커밋할 것이 없다.
_WRITE_METHOD_BUT_READ_ONLY: dict[str, str] = {
    "/api/v1/auth/login": "자격 검증 후 토큰만 발급한다 — DB 변경 없음",
    "/api/v1/auth/refresh": "refresh 토큰 검증 후 재발급만 한다 — DB 변경 없음",
}


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


def _read_routes() -> list[APIRoute]:
    return [
        r for r in _api_routes() if r.methods and r.methods <= {"GET", "HEAD", "OPTIONS"}
    ]


def _write_routes() -> list[APIRoute]:
    return [r for r in _api_routes() if r.methods and r.methods & _WRITE_METHODS]


def test_read_routes_do_not_use_write_dependencies():
    """조회 라우트는 쓰기용 서비스 의존성을 쓰지 않는다."""
    offenders = [
        (route.path, sorted(d.__name__ for d in _dependency_calls(route) & _WRITE_DEPENDENCIES))
        for route in _read_routes()
        if _dependency_calls(route) & _WRITE_DEPENDENCIES
    ]

    assert not offenders, (
        f"조회 라우트가 쓰기용 의존성을 사용함: {offenders}. "
        "get_<name>_service_readonly 로 바꿀 것."
    )


def test_read_routes_do_not_use_writer_session():
    """조회 라우트는 쓰기 세션을 쓰지 않는다.

    커밋을 안 하더라도 writer 세션을 잡으면 조회가 replica 로 분산되지 않는다.
    """
    offenders = [
        route.path
        for route in _read_routes()
        if get_session in _dependency_calls(route)
        and route.path not in _WRITER_SESSION_BY_DESIGN
    ]

    assert not offenders, (
        f"조회 라우트가 쓰기 세션(get_session)을 사용함: {sorted(offenders)}. "
        "get_read_session 으로 바꾸거나, 복제 지연을 허용할 수 없는 조회라면 "
        "_WRITER_SESSION_BY_DESIGN 에 이유와 함께 추가할 것."
    )


def test_write_routes_use_write_dependencies():
    """쓰기 라우트는 쓰기용 의존성을 쓴다.

    읽기 분리 작업 중 쓰기까지 read-only 로 바꿔버리면 ReadOnlyRoutingError 가 나거나
    데이터가 저장되지 않는다. 반대 방향 사고를 막는 짝 테스트다.
    """
    missing = [
        route.path
        for route in _write_routes()
        if not (_dependency_calls(route) & _WRITE_DEPENDENCIES)
    ]

    assert not missing, f"쓰기 라우트에 쓰기용 의존성이 없다: {missing}"


def test_write_routes_commit_inside_handler():
    """쓰기 라우트는 핸들러 본문에서 커밋한다 (P1-3).

    의존성 teardown 커밋은 FastAPI 상위 버전에서 응답 전송 후에 실행되어, 커밋이
    실패해도 클라이언트가 성공 응답을 받는다. 커밋은 반드시 핸들러 안에 있어야 한다.

    핸들러 소스에 커밋 호출이 있는지 본다. 정교하지는 않지만 "커밋을 아예 빠뜨린"
    가장 흔한 사고를 잡기에는 충분하고, 런타임 픽스처 없이 전 도메인을 덮는다.
    """
    offenders = []
    for route in _write_routes():
        if route.path in _WRITE_METHOD_BUT_READ_ONLY:
            continue
        source = inspect.getsource(route.endpoint)
        if "commit()" not in source:
            offenders.append(f"{sorted(route.methods)} {route.path}")

    assert not offenders, (
        f"쓰기 핸들러에 커밋이 없다: {offenders}. "
        "핸들러 본문에서 await service.commit() 을 호출할 것. "
        "DB를 쓰지 않는 라우트라면 _WRITE_METHOD_BUT_READ_ONLY 에 이유와 함께 추가할 것."
    )


def test_allowlists_are_not_stale():
    """allowlist 에 적힌 경로가 실제로 존재하는지 확인한다."""
    paths = {r.path for r in _api_routes()}

    stale = (set(_WRITER_SESSION_BY_DESIGN) | set(_WRITE_METHOD_BUT_READ_ONLY)) - paths

    assert not stale, f"존재하지 않는 경로가 allowlist 에 남음: {sorted(stale)}"


def test_coverage_is_not_vacuous():
    """검사 대상이 실제로 존재하는지 확인한다.

    라우팅이 바뀌어 _api_routes() 가 비면 위 테스트들은 조용히 통과한다.
    """
    assert len(_read_routes()) >= 14, (
        f"조회 라우트가 {len(_read_routes())}개뿐 — 검사가 비었을 수 있다"
    )
    assert len(_write_routes()) >= 15, (
        f"쓰기 라우트가 {len(_write_routes())}개뿐 — 검사가 비었을 수 있다"
    )
