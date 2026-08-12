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
    것만으로 관리 화면이 딸려 와, ADMIN=false 인데도 sqladmin 과 ModelView 가 전부
    메모리에 올라간다(ADMIN-2, 실측). 그러면 ADMIN=false 는 "라우트만 안 붙임" 이 되고,
    sqladmin 을 선택적 의존성으로 분리할 수도 없다. 재노출된 이름을 읽는 코드는 앱에
    하나도 없었으므로 비용만 남는 별명이었다.
    회귀 가드: ``tests/test_admin_wiring.py`` 의 ADMIN=false 미로드 검사.

조립 구조:
    ``main.py`` 는 ADMIN=true 일 때 ``register_admin(app, engine)`` **하나만** 호출하고,
    그 안에서 두 단계로 나뉜다. 아래 두 함수는 SQLAdmin 이나 FastAPI 의 공식 API 가 아니라
    **이 프로젝트 내부의 조립 함수**다.

        register_admin(app, engine)          ← main.py 가 부르는 유일한 진입점
          ├─ create_admin_interface(...)     Admin 생성 + /admin 마운트
          └─ register_admin_views(admin)     ADMIN_VIEWS 등록
               └─ ADMIN_VIEWS                등록 대상 SSOT

    나눈 이유는 두 책임이 서로 다른 것을 알아야 하기 때문이다 — 생성 쪽은 앱·엔진·제목
    (그리고 나중에 인증 백엔드)을 알아야 하고, 등록 쪽은 뷰 목록만 알면 된다. 나뉘어
    있으면 각각 단독으로 검증할 수 있다.

URL 등록:
    ``/admin`` 라우트는 ``create_admin_interface()`` 안에서 ``Admin(app, engine, ...)`` 이
    생성되는 순간 SQLAdmin 이 직접 마운트한다. 별도의 ``include_router()`` 나 URL 패턴
    등록은 필요하지 않다 — 찾아도 안 나오는 이유가 이것이다.

Note:
    SQLAdmin 은 ADMIN 설정으로 제어된다 (DEBUG 와 독립적).
    ADMIN=True: /admin 접근 가능, ADMIN=False: /admin 접근 차단.
    운영 환경에서는 보안상 ADMIN=False 설정을 권장한다.

보안 주의 (이 저장소 고유):
    ``User`` 는 자격증명(``hashed_password``)을 보유한다. sqladmin 은
    ``column_details_list`` / ``form_columns`` 를 지정하지 않으면 상세·수정 폼에
    **모델의 모든 컬럼**을 넣으므로, ``app/features/user/admin.py`` 의 제외 설정을
    지우면 bcrypt 해시가 관리 화면·내보내기에 노출된다 — 지우지 말 것.
    구조 증거: ``tests/core/test_admin_views.py``.
"""

from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqlalchemy.ext.asyncio import AsyncEngine

from app.features.blog.admin import admin_views as blog_admin_views
from app.features.home.admin import admin_views as home_admin_views
from app.features.reply.admin import admin_views as reply_admin_views
from app.features.sns.admin import admin_views as sns_admin_views
from app.features.user.admin import admin_views as user_admin_views
from config import app_settings

# 등록 대상 뷰 목록 (SSOT). auth 는 자체 모델이 없어 관리 화면도 없다.
ADMIN_VIEWS: list[type[ModelView]] = [
    *blog_admin_views,
    *home_admin_views,
    *reply_admin_views,
    *sns_admin_views,
    *user_admin_views,
]


def create_admin_interface(app: FastAPI, engine: AsyncEngine) -> Admin:
    """SQLAdmin 인터페이스를 만들고 FastAPI 앱에 마운트한다.

    **뷰는 등록하지 않는다** — 그것은 ``register_admin_views()`` 의 몫이다.
    여기서 ``Admin(...)`` 을 생성하는 순간 SQLAdmin 이 ``/admin`` 라우트를 붙인다.

    향후 인증 정책이 승인되면 ``authentication_backend`` 를 **이 함수 안에서** 주입한다.
    인증 백엔드는 ``Admin`` 생성 인자라서 뷰 등록 쪽으로는 넣을 수 없다.
    (현재는 인증을 도입하지 않는 것이 확정 방침이다 — 모듈 docstring 의 보안 주의 참고.)

    Args:
        app: FastAPI 인스턴스.
        engine: SQLAlchemy async 엔진.

    Returns:
        뷰가 아직 등록되지 않은 ``Admin`` 인스턴스.
    """
    return Admin(app, engine, title=f"{app_settings.PROJECT_NAME} Admin")


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
