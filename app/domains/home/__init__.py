"""Home 도메인 패키지.

표준 FastAPI 구조: 이 패키지가 하위 뷰 라우터를 취합한 ``router`` 를 공개하며,
``main.py`` 가 이를 ``include_router`` 로 최종 취합한다.

import-time 부수효과로 access-log sink 를 미들웨어에 등록한다.
모델 모듈을 import 하여 ``Base.metadata`` 에 테이블을 등록한다.
"""

from app.domains.home.access_log_sink import register_sink
from app.domains.home.admin import admin_views
from app.domains.home.api.routers.router import home_router as router
from app.domains.home.models import models as _models  # noqa: F401  (Base.metadata 등록)

register_sink()

__all__ = ["router", "admin_views"]
