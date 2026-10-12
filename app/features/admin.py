"""SQLAdmin 등록 지점 — 기능별 ``admin.py`` 를 명시적으로 취합한다.

``ModelView`` 정의는 각 기능이 소유한다(``app/features/<name>/admin.py``). 모델과 그
관리 화면이 같은 폴더에 있어야 컬럼이 바뀔 때 함께 눈에 들어오고, 기능을 통째로
복사·삭제할 때 관리 화면이 따라온다. 이 파일은 그것들을 모아 등록만 한다.

수집은 **명시적 import** 로 한다 — 디렉터리 스캔이나 ``getattr(module, "admin_views", [])``
같은 관용적 수집은 쓰지 않는다. 과거 그 방식이었을 때 기능의 ``admin.py`` 가 0바이트
빈 파일이어도 조용히 건너뛰어져, ``/admin`` 은 정상 마운트된 채 등록 뷰만 1개인 상태를
아무도 눈치채지 못했다(ADMIN-1). 명시 import 는 파일이 없거나 ``admin_views`` 가 빠지면
기동 시점에 ImportError 로 즉시 터진다.

새 기능의 관리 화면을 추가하려면:
    1. ``app/features/<name>/admin.py`` 에 ModelView 와 ``admin_views`` 를 만든다.
    2. 이 파일의 import 와 ``ADMIN_VIEWS`` 에 한 줄씩 더한다.

기능 패키지 ``__init__.py`` 로는 재노출하지 않는다:
    수집은 위처럼 ``app.features.<name>.admin`` **모듈**에서 직접 한다. 패키지가
    ``admin_views`` 를 재노출하면 ``main.py`` 가 라우터를 얻으려고 패키지를 import 하는
    것만으로 관리 화면이 딸려 와, ADMIN_DISABLED=true 인데도 sqladmin 과 ModelView 가 전부
    메모리에 올라간다(ADMIN-2, 실측). 그러면 ADMIN_DISABLED=true 는 "라우트만 안 붙임" 이 되고,
    sqladmin 을 선택적 의존성으로 분리할 수도 없다. 재노출된 이름을 읽는 코드는 앱에
    하나도 없었으므로 비용만 남는 별명이었다.
    회귀 가드: ``tests/test_admin_wiring.py`` 의 ADMIN_DISABLED=true 미로드 검사.

조립 구조:
    ``main.py`` 는 ADMIN_DISABLED 가 아닐 때 ``register_admin(app, engine)`` **하나만** 호출하고,
    그 안에서 두 단계로 나뉜다. 아래 두 함수는 SQLAdmin 이나 FastAPI 의 공식 API 가 아니라
    **이 프로젝트 내부의 조립 함수**다.

        register_admin(app, engine)          ← main.py 가 부르는 유일한 진입점
          ├─ create_admin_interface(...)     Admin 생성 + /admin 마운트
          └─ register_admin_views(admin)     ADMIN_VIEWS 등록
               └─ ADMIN_VIEWS                등록 대상 SSOT

    나눈 이유는 두 책임이 서로 다른 것을 알아야 하기 때문이다 — 생성 쪽은 앱·엔진·제목·
    인증 백엔드·템플릿 위치를 알아야 하고, 등록 쪽은 뷰 목록만 알면 된다. 나뉘어 있으면
    각각 단독으로 검증할 수 있다.

URL 등록:
    ``/admin`` 라우트는 ``create_admin_interface()`` 안에서 ``Admin(app, engine, ...)`` 이
    생성되는 순간 SQLAdmin 이 직접 마운트한다. 별도의 ``include_router()`` 나 URL 패턴
    등록은 필요하지 않다 — 찾아도 안 나오는 이유가 이것이다.

Note:
    SQLAdmin 은 ADMIN_DISABLED 설정으로 끈다 (DEBUG 와 독립적, admin-login ADR-005).
    기본(false): /admin 마운트, true: 마운트·sqladmin import·세션 미들웨어·인증 백엔드가
    모두 없다(404) — 앱 응답·기동 로그에도 관리 화면 경로가 나오지 않는다.

로그인 (admin-login ADR-001~003):
    ``/admin`` 은 **활성 슈퍼유저** 로그인이 필요하다 — ``AdminAuthBackend``
    (``app/features/auth/admin_backend.py``)를 ``create_admin_interface()`` 가 주입한다.
    계정은 ``scripts/create_superuser.py`` 로 만든다. 세션 쿠키는 ``admin_session``
    (``SESSION_SECRET_KEY`` 로 서명, path ``/admin``, SameSite=Strict, HttpOnly, 8시간,
    staging/production 은 Secure). 로그인 화면은 ``app/templates/admin/sqladmin/login.html``
    (Bootstrap) 이 SQLAdmin 기본 화면을 덮어쓴다 — ``templates_dir`` 의 FileSystemLoader 가
    SQLAdmin 패키지 템플릿보다 먼저 찾아진다.

보안 주의 (이 저장소 고유):
    ``User`` 는 자격증명(``hashed_password``)을 보유한다. sqladmin 은
    ``column_details_list`` / ``form_columns`` 를 지정하지 않으면 상세·수정 폼에
    **모델의 모든 컬럼**을 넣으므로, ``app/features/user/admin.py`` 의 제외 설정을
    지우면 비밀번호 해시가 관리 화면·내보내기에 노출된다 — 지우지 말 것.
    구조 증거: ``tests/core/test_admin_views.py``.
"""

from pathlib import Path

from fastapi import FastAPI
from redis.asyncio import Redis
from sqladmin import Admin, ModelView
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from starlette.requests import Request

from app.core.db.session import background_db_session
from app.core.exception import ServiceUnavailableException
from app.core.middlewares.client_ip import ClientIPResolver
from app.core.security.dependencies import (
    get_password_hasher,
    get_refresh_token_store,
    get_token_service,
)
from app.core.security.rate_limit import RateLimiter
from app.features.auth.admin_backend import AdminAuthBackend, SessionFactory
from app.features.auth.dependencies.auth_dependencies import get_rate_limiter
from app.features.auth.services.auth_service import AuthService
from app.features.blog.admin import admin_views as blog_admin_views
from app.features.catalog.admin import admin_views as catalog_admin_views
from app.features.home.admin import admin_views as home_admin_views
from app.features.reply.admin import admin_views as reply_admin_views
from app.features.reports.admin import admin_views as reports_admin_views
from app.features.sns.admin import admin_views as sns_admin_views
from app.features.user.admin import admin_views as user_admin_views
from config import DEPLOYED_ENVS, app_settings, middleware_settings, session_settings

# 등록 대상 뷰 목록 (SSOT). auth 는 자체 모델이 없어 관리 화면도 없다.
# 순서는 기능명 사전순 — 사이드바 메뉴 순서가 곧 이 순서이고,
# tests/test_admin_wiring.py 가 기능 디렉터리에서 만든 목록과 순서까지 대조한다.
ADMIN_VIEWS: list[type[ModelView]] = [
    *blog_admin_views,
    *catalog_admin_views,
    *home_admin_views,
    *reply_admin_views,
    *reports_admin_views,
    *sns_admin_views,
    *user_admin_views,
]


# 로그인 화면(sqladmin/login.html) 덮어쓰기 위치. 작업 디렉터리와 무관하게 절대 경로로 준다.
ADMIN_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "admin"


def _app_redis(app: FastAPI) -> Redis:
    """바깥 FastAPI 앱의 lifespan 이 연 Redis.

    SQLAdmin 은 하위 Starlette 앱으로 마운트돼 ``request.app`` 이 그 하위 앱을 가리킨다 —
    ``get_redis(request)`` 로는 ``app.state.redis`` 에 닿지 않아 바깥 앱을 직접 본다.
    """
    client: Redis | None = getattr(app.state, "redis", None)
    if client is None:
        raise ServiceUnavailableException("Redis 를 사용할 수 없습니다.")
    return client


def build_admin_auth_backend(
    app: FastAPI, session_factory: SessionFactory = background_db_session
) -> AdminAuthBackend:
    """기존 provider 로 ``AdminAuthBackend`` 를 조립한다(service-hardening C-1).

    Args:
        app: Redis 를 ``app.state`` 에 들고 있는 바깥 FastAPI 앱.
        session_factory: 요청 밖 DB 세션. 테스트는 다른 DB 의 세션을 넣는다.
    """

    def auth_service(_request: Request, db_session: AsyncSession) -> AuthService:
        return AuthService(
            db_session,
            get_password_hasher(),
            get_token_service(),
            get_refresh_token_store(_app_redis(app)),
        )

    def rate_limiter(_request: Request) -> RateLimiter:
        return get_rate_limiter(_app_redis(app))

    return AdminAuthBackend(
        secret_key=session_settings.SESSION_SECRET_KEY,
        https_only=app_settings.ENV in DEPLOYED_ENVS,
        session_factory=session_factory,
        auth_service_factory=auth_service,
        rate_limiter_factory=rate_limiter,
        client_ip_resolver=ClientIPResolver(middleware_settings.TRUSTED_PROXY_HOPS),
    )


def create_admin_interface(
    app: FastAPI,
    engine: AsyncEngine,
    authentication_backend: AdminAuthBackend | None = None,
) -> Admin:
    """SQLAdmin 인터페이스를 만들고 FastAPI 앱에 마운트한다.

    **뷰는 등록하지 않는다** — 그것은 ``register_admin_views()`` 의 몫이다.
    여기서 ``Admin(...)`` 을 생성하는 순간 SQLAdmin 이 ``/admin`` 라우트를 붙인다.

    인증 백엔드와 로그인 템플릿 위치는 ``Admin`` 생성 인자라서 **이 함수 안에서** 주입한다
    (뷰 등록 쪽으로는 넣을 수 없다). 백엔드는 생성된 ``Admin`` 의 템플릿 환경을 받아 400·429
    로그인 화면을 같은 템플릿으로 그린다.

    Args:
        app: FastAPI 인스턴스.
        engine: SQLAlchemy async 엔진.
        authentication_backend: 생략하면 ``build_admin_auth_backend(app)``.

    Returns:
        뷰가 아직 등록되지 않은 ``Admin`` 인스턴스.
    """
    backend = authentication_backend or build_admin_auth_backend(app)
    admin = Admin(
        app,
        engine,
        title=f"{app_settings.PROJECT_NAME} Admin",
        authentication_backend=backend,
        templates_dir=str(ADMIN_TEMPLATES_DIR),
    )
    backend.templates = admin.templates
    return admin


def register_admin_views(admin: Admin) -> None:
    """``ADMIN_VIEWS`` 의 모든 ModelView 를 선언 순서대로 등록한다.

    이 함수는 목록을 **만들지 않는다.** 디렉터리 스캔도, 예외 무시도 하지 않는다.
    등록 대상의 진실은 ``ADMIN_VIEWS`` 하나뿐이고 여기서는 그대로 옮길 뿐이다.
    FastAPI 앱·엔진·설정을 참조하지 않으므로 임의의 ``Admin`` 으로 단독 검증할 수 있다.

    Args:
        admin: ``create_admin_interface()`` 가 만든 인스턴스.
    """
    for view in ADMIN_VIEWS:
        admin.add_view(view)


def register_admin(app: FastAPI, engine: AsyncEngine) -> Admin:
    """관리자 인터페이스를 만들고 프로젝트의 ModelView 를 등록한다.

    **애플리케이션 조립부(`main.py`)가 호출하는 유일한 진입점.** 위 두 함수를
    직접 부르지 않게 해서, 조립부가 SQLAdmin 의 생성·등록 순서를 알 필요가 없게 한다.

    Args:
        app: FastAPI 인스턴스.
        engine: SQLAlchemy async 엔진.

    Returns:
        구성된 ``Admin`` 인스턴스(테스트에서 등록 뷰를 검사할 수 있도록 반환).
    """
    admin = create_admin_interface(app, engine)
    register_admin_views(admin)
    return admin
