"""Home 기능 패키지.

표준 FastAPI 구조: 이 패키지가 하위 뷰 라우터를 취합한 ``router`` 를 공개하며,
``main.py`` 가 이를 ``include_router`` 로 최종 취합한다.

import-time 부수효과로 access-log sink 를 미들웨어에 등록한다.
모델 모듈을 import 하여 ``Base.metadata`` 에 테이블을 등록한다.

``admin_views`` 는 재노출하지 않는다 — 이유는 ``app/features/admin.py`` 참고.
"""

from app.features.home.access_log_sink import register_sink
from app.features.home.api.routers.router import home_router as router
from app.features.home.models import models as _models  # noqa: F401  (Base.metadata 등록)

register_sink()

__all__ = ["router"]
