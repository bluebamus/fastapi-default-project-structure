"""SNS 기능 패키지.

하위 뷰 라우터를 취합한 ``router`` 를 공개한다. ``main.py`` 가 ``include_router`` 로 취합한다.
모델 모듈을 import 하여 ``Base.metadata`` 에 테이블을 등록한다.

``admin_views`` 는 재노출하지 않는다 — 이유는 ``app/features/admin.py`` 참고.
"""

from app.features.sns.api.routers.router import sns_router as router
from app.features.sns.models import models as _models  # noqa: F401  (Base.metadata 등록)

__all__ = ["router"]
