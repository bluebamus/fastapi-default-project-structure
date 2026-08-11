"""UserProfile 도메인 패키지.

하위 뷰 라우터를 취합한 ``router`` 와 ``admin_views`` 를 공개한다. main.py 의 APPS
목록에 이 패키지를 추가하면 라우터가 /api 에, admin_views 가 SQLAdmin 에 등록된다.

모델을 추가하면 아래 import 주석을 해제해 ``Base.metadata`` 에 등록한다:
    from app.features.user_profile.models import models as _models  # noqa: F401
"""
from app.features.user_profile.admin import admin_views
from app.features.user_profile.api.routers.router import user_profile_router as router

__all__ = ["router", "admin_views"]
