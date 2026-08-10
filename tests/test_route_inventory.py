"""라우트 인벤토리 골든 스냅샷 (리팩토링 회귀 방지 안전망).

Django식 AppRegistry 자동발견 → 표준 FastAPI include_router 배선으로 재구조화하는 동안
공개 API 경로/메서드가 바뀌지 않았음을 보장한다. DEBUG/ADMIN 설정에 따라 달라지는
/docs·/openapi.json·/admin 은 제외하고, 항상 존재하는 도메인 API + /health 만 고정한다.

경로 수집에는 `app.openapi()` 를 쓴다. `app.routes` 직접 순회는 FastAPI 버전에 따라
하위 라우터가 평탄화되지 않아(0.141 의 `_IncludedRouter`) 깨진다. OpenAPI 스키마는
공개 API 이고 버전 간 형태가 안정적이다.
"""

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
    # auth 도메인 (Phase B)
    "/api/v1/auth/register": frozenset({"POST"}),
    "/api/v1/auth/login": frozenset({"POST"}),
    "/api/v1/auth/refresh": frozenset({"POST"}),
    "/api/v1/auth/me": frozenset({"GET"}),
}


def _collect_api_routes() -> dict[str, frozenset[str]]:
    from main import app

    return {
        path: frozenset(method.upper() for method in operations)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api") or path == "/health"
    }


def test_route_inventory_matches_golden():
    assert _collect_api_routes() == EXPECTED
