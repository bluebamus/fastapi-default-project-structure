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

from slowapi import Limiter
from slowapi.util import get_remote_address

from config import middleware_settings

limiter = Limiter(
    key_func=get_remote_address,
    enabled=middleware_settings.RATE_LIMIT_ENABLED,
)
