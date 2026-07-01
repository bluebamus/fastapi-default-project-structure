"""라우트 인벤토리 골든 스냅샷 (리팩토링 회귀 방지 안전망).

Django식 AppRegistry 자동발견 → 표준 FastAPI include_router 배선으로 재구조화하는 동안
공개 API 경로/메서드가 바뀌지 않았음을 보장한다. DEBUG/ADMIN 설정에 따라 달라지는
/docs·/openapi.json·/admin 은 제외하고, 항상 존재하는 도메인 API + /health 만 고정한다.
"""

from collections import defaultdict

# 재구조화 이전 baseline 에서 캡처한 골든 경로 집합 (경로 -> 허용 메서드).
EXPECTED: dict[str, frozenset[str]] = {
    "/health": frozenset({"GET"}),
    "/api/v1/home/access-logs": frozenset({"GET"}),
    "/api/v1/home/access-logs/recent": frozenset({"GET"}),
    "/api/v1/home/access-logs/by-ip/{ip_address}": frozenset({"GET"}),
    "/api/v1/home/access-logs/by-user/{user_id}": frozenset({"GET"}),
    "/api/v1/home/access-logs/stats": frozenset({"GET"}),
    "/api/v1/blog/posts": frozenset({"GET", "POST"}),
    "/api/v1/blog/posts/{post_id}": frozenset({"GET", "PATCH", "DELETE"}),
    "/api/v1/reply/replies": frozenset({"GET", "POST"}),
    "/api/v1/reply/replies/{reply_id}": frozenset({"GET", "PATCH", "DELETE"}),
    "/api/v1/sns/posts": frozenset({"GET", "POST"}),
    "/api/v1/sns/posts/{post_id}": frozenset({"GET", "PATCH", "DELETE"}),
    "/api/v1/user/users": frozenset({"GET", "POST"}),
    "/api/v1/user/users/{user_id}": frozenset({"GET", "PATCH", "DELETE"}),
}


def _collect_api_routes() -> dict[str, frozenset[str]]:
    from main import app

    got: dict[str, set[str]] = defaultdict(set)
    for r in app.routes:
        path = getattr(r, "path", None)
        if not path:
            continue
        if path.startswith("/api") or path == "/health":
            got[path] |= set(getattr(r, "methods", None) or [])
    return {p: frozenset(m) for p, m in got.items()}


def test_route_inventory_matches_golden():
    assert _collect_api_routes() == EXPECTED
