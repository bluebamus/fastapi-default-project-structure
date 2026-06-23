"""앱 수동 등록 단일 진실 공급원(SSOT).

도메인 앱의 라우터·모델·Admin·Celery 패키지를 이 모듈에서 명시적으로 등록한다.
자동 발견(pkgutil/inspect 스캔)을 사용하지 않으며, 새 도메인 앱을 추가할 때는
아래 함수/리스트에 직접 항목을 추가한다.

소비처:
    - app/core/bootstrap.py: routers(), admin_views(), register_models()
    - app/core/celery/app.py: CELERY_TASK_MODULES, BEAT_SCHEDULE
    - app/core/db/session.py: register_models()
    - migrations/env.py: register_models()
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from fastapi import APIRouter


@dataclass(frozen=True)
class RouterSpec:
    """FastAPI에 마운트할 라우터와 그 프리픽스."""

    router: APIRouter
    prefix: str = "/api"


# ---------------------------------------------------------------------------
# 라우터 등록
# ---------------------------------------------------------------------------


def routers() -> list[RouterSpec]:
    """FastAPI에 마운트할 라우터 명세 목록을 반환한다.

    라우터는 지연 import 한다(모듈 로드 시점 부수효과/순환참조 방지).

    Note:
        home_router 를 반환하기 전에 access-log sink 를 명시적으로 등록한다.
        (기존 home/config.py 의 set_access_log_sink 부수효과를 보존하기 위함)

    Returns:
        RouterSpec 목록.
    """
    from app.domains.home.access_log_sink import register_sink

    register_sink()

    from app.domains.home.api.routers.router import home_router

    return [
        RouterSpec(router=home_router, prefix="/api"),
    ]


# ---------------------------------------------------------------------------
# 모델 등록 (Base.metadata 채움 — create_db_tables / Alembic 공용)
# ---------------------------------------------------------------------------

_MODEL_MODULES = [
    "app.domains.home.models.models",
]


def register_models() -> None:
    """모든 도메인 모델 모듈을 import 하여 Base.metadata 에 등록한다.

    정적 경로 목록(_MODEL_MODULES)을 순회 import 한다. 동적 스캔은 하지 않는다.
    """
    for module_path in _MODEL_MODULES:
        importlib.import_module(module_path)


# ---------------------------------------------------------------------------
# Admin 뷰 등록
# ---------------------------------------------------------------------------


def admin_views() -> list[type]:
    """SQLAdmin 에 등록할 ModelView 클래스 목록을 반환한다.

    Returns:
        ModelView 서브클래스 목록.
    """
    from app.domains.home.admin import UserAccessLogAdmin

    return [UserAccessLogAdmin]


# ---------------------------------------------------------------------------
# Celery 등록
# ---------------------------------------------------------------------------

# 태스크는 명시적 모듈 경로로 등록한다(autodiscover 미사용 — _MODEL_MODULES 와 대칭).
# Celery 가 이 모듈들을 import 하면 @celery_app.task 데코레이터가 태스크를 등록한다.
CELERY_TASK_MODULES = ["app.domains.home.worker.tasks"]

BEAT_SCHEDULE: dict = {}
