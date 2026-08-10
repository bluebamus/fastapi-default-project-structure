"""레이트 리밋(slowapi) — 데코레이터 기반 limiter.

전역 미들웨어(SlowAPIMiddleware)는 사용하지 않는다. 라우트 함수에 `@limiter.limit(...)`
데코레이터를 붙이고 `request: Request` 파라미터를 두어 라우트별로 한도를 적용한다. 예:

    from app.core.rate_limit import limiter
    from config import middleware_settings

    @router.post("/login")
    @limiter.limit(middleware_settings.RATE_LIMIT_DEFAULT)
    async def login(request: Request, ...): ...

활성화는 `config.middleware_settings.RATE_LIMIT_ENABLED`로 제어한다(비활성 시 데코레이터는
무동작). 기본 한도 문자열은 `RATE_LIMIT_DEFAULT`. `main.py` 가 `app.state.limiter` 와
`RateLimitExceeded` 예외 핸들러를 등록한다.
테스트에서는 RATE_LIMIT_ENABLED=false 로 비활성화된다(in-memory 카운터 공유 방지).
"""

from fastapi import Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import middleware_settings

limiter = Limiter(
    key_func=get_remote_address,
    enabled=middleware_settings.RATE_LIMIT_ENABLED,
)


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    """Starlette `add_exception_handler()` 시그니처에 맞춘 위임 래퍼.

    slowapi 의 `_rate_limit_exceeded_handler` 는 두 번째 인자를 `RateLimitExceeded` 로
    좁혀 선언해서 Starlette 이 기대하는 `(Request, Exception)` 계약과 정적으로 맞지
    않는다(mypy arg-type). `cast()` 로 덮으면 타입만 가려지고 실제 전달값은 검증되지
    않으므로, 여기서 실제로 좁힌 뒤 위임한다.

    등록된 예외 클래스와 다른 예외가 들어오는 것은 라우팅 버그이므로 삼키지 않고
    그대로 전파한다.
    """
    if not isinstance(exc, RateLimitExceeded):
        raise exc
    return _rate_limit_exceeded_handler(request, exc)
