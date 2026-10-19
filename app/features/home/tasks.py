"""Home 기능 Celery 태스크.

워커는 ``app/core/db/models_registry.py`` 의 ``iter_task_modules()`` 로 이 모듈을 찾아 include 한다
(service-hardening ADR-012) — 중앙 목록에 적을 곳이 없다. 이 기능을 지우면 이 태스크도 함께 빠진다.

요청 밖 세션은 ``background_db_session`` 으로 열고, 서비스 조립은 HTTP 경로와 같은 provider
(``build_user_access_log_service``)를 재사용한다. 쓰기 태스크라면 태스크가 직접 커밋한다.

주기 실행은 이 모듈이 ``celery_app.conf.beat_schedule`` 에 **스스로** 등록한다(security-ops-hardening ADR-003) —
중앙 Celery 앱은 기능을 모르고, beat 도 기동 시 include 모듈을 import 하므로 여기 등록이 보인다.
"""

from typing import Any

from celery.schedules import crontab

from app.celery.app import celery_app
from app.celery.task import run_async
from app.core.db.session import background_db_session
from app.features.home.dependencies.access_log_dependencies import (
    build_access_log_retention_service,
    build_user_access_log_service,
)

PURGE_TASK_NAME = "home.purge_expired_access_logs"
# 하루 한 번, 업무 시간대(TIME_ZONE — celery_app.conf.timezone) 새벽.
PURGE_SCHEDULE = crontab(hour=3, minute=30)


@celery_app.task(name="home.aggregate_access_stats")
def aggregate_access_stats() -> dict[str, Any]:
    """접속 로그 통계를 집계하여 반환한다(예시 태스크)."""

    async def _run() -> dict[str, Any]:
        async with background_db_session() as db_session:
            stats = await build_user_access_log_service(db_session).get_stats()
            return {"total": stats.total_count}

    result: dict[str, Any] = run_async(_run())
    return result


@celery_app.task(name=PURGE_TASK_NAME)
def purge_expired_access_logs() -> int:
    """보존 기간(``ACCESS_LOG_RETENTION_DAYS``)이 지난 접속 로그를 지우고 지운 행 수를 돌려준다."""

    async def _run() -> int:
        async with background_db_session() as db_session:
            return await build_access_log_retention_service(db_session).purge()

    deleted: int = run_async(_run())
    return deleted


celery_app.conf.beat_schedule[PURGE_TASK_NAME] = {
    "task": PURGE_TASK_NAME,
    "schedule": PURGE_SCHEDULE,
}
