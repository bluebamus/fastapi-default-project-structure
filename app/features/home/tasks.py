"""Home 기능 Celery 태스크.

워커는 ``app/core/db/models_registry.py`` 의 ``iter_task_modules()`` 로 이 모듈을 찾아 include 한다
(service-hardening ADR-012) — 중앙 목록에 적을 곳이 없다. 이 기능을 지우면 이 태스크도 함께 빠진다.

요청 밖 세션은 ``background_db_session`` 으로 열고, 서비스 조립은 HTTP 경로와 같은 provider
(``build_user_access_log_service``)를 재사용한다. 쓰기 태스크라면 태스크가 직접 커밋한다.
"""

from typing import Any

from app.celery.app import celery_app
from app.celery.task import run_async
from app.core.db.session import background_db_session
from app.features.home.dependencies.access_log_dependencies import build_user_access_log_service


@celery_app.task(name="home.aggregate_access_stats")
def aggregate_access_stats() -> dict[str, Any]:
    """접속 로그 통계를 집계하여 반환한다(예시 태스크)."""

    async def _run() -> dict[str, Any]:
        async with background_db_session() as db_session:
            stats = await build_user_access_log_service(db_session).get_stats()
            return {"total": stats.total_count}

    result: dict[str, Any] = run_async(_run())
    return result
