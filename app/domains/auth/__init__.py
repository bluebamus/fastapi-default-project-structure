"""Auth 도메인 패키지 — OAuth2 password flow + JWT.

하위 뷰 라우터를 취합한 ``router`` 를 공개한다. main.py 의 APPS 가 include_router 로 취합한다.
자체 모델은 없으며 user 도메인의 ``User`` 에 대해 인증한다(자격증명은 users.hashed_password).
"""

from app.domains.auth.api.routers.router import auth_router as router

__all__ = ["router"]
