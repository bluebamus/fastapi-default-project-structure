"""
Home 도메인 Celery 태스크.

이 모듈은 Home 도메인의 백그라운드 작업을 정의한다.
"""

from app.core.celery.app import celery_app
from app.core.celery.task import run_async
from app.domains.home.services.user_access_log_service import UserAccessLogService
from app.domains.home.unit_of_work import HomeUnitOfWork


@celery_app.task(name="home.aggregate_access_stats")
def aggregate_access_stats() -> dict:
    """접속 로그 통계를 집계하여 반환한다."""

    async def _run() -> dict:
        async with HomeUnitOfWork(background=True) as uow:
            stats = await UserAccessLogService(uow).get_stats()
            return {"total": stats.total_count}

    return run_async(_run())
