"""레이트 리밋(slowapi) 데코레이터 방식 통합 테스트.

전역 앱(main.app)은 in-memory 카운터가 테스트 간 공유되므로 테스트에선 비활성화된다
(pyproject: RATE_LIMIT_ENABLED=false). 여기서는 main.py 와 동일한 배선(app.state.limiter +
app.core.rate_limit.rate_limit_exceeded_handler)과 `@limiter.limit` 데코레이터를 격리된
앱으로 구성해 429 동작을 검증한다.

핸들러는 main.py 가 실제로 등록하는 래퍼를 그대로 쓴다. slowapi 원본 핸들러를 직접
쓰면 이 테스트가 운영 배선과 갈라져, 래퍼가 깨져도 초록으로 남는다.
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.rate_limit import rate_limit_exceeded_handler


def _build_app(limit: str, *, enabled: bool = True) -> FastAPI:
    limiter = Limiter(key_func=get_remote_address, enabled=enabled)
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    @app.get("/ping")
    @limiter.limit(limit)
    async def ping(request: Request) -> dict:
        return {"ok": True}

    return app


def test_rate_limit_returns_429_after_threshold():
    client = TestClient(_build_app("3/minute"))
    codes = [client.get("/ping").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429
    assert codes[4] == 429


def test_rate_limit_disabled_allows_all():
    client = TestClient(_build_app("2/minute", enabled=False))
    codes = [client.get("/ping").status_code for _ in range(6)]
    assert all(code == 200 for code in codes)


def test_handler_reraises_unexpected_exception():
    """래퍼는 RateLimitExceeded 가 아닌 예외를 429 로 감추지 않고 전파한다.

    타입을 cast 로 덮는 대신 실제로 좁히는 이유가 이것이다. 잘못 등록된 예외가
    조용히 429 응답으로 둔갑하면 원인 추적이 불가능해진다.
    """
    boom = ValueError("not a rate limit error")
    with pytest.raises(ValueError, match="not a rate limit error"):
        rate_limit_exceeded_handler(Request({"type": "http", "headers": []}), boom)
