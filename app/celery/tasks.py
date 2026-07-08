"""중앙 Celery 태스크 모듈.

앱별 worker/ 를 대체하는 단일 태스크 모듈. 도메인 백그라운드 작업을 여기 정의한다.
celery_app.conf.include = ["app.celery.tasks"] 로 등록된다.
요청 밖 세션은 background_session 컨텍스트로 관리한다(UnitOfWork 제거).
"""

from typing import Any

from app.celery.app import celery_app
from app.celery.task import run_async
from app.core.db.session import background_session
from app.domains.home.services.user_access_log_service import UserAccessLogService


@celery_app.task(name="home.aggregate_access_stats")
def aggregate_access_stats() -> dict[str, Any]:
    """접속 로그 통계를 집계하여 반환한다(예시 태스크)."""

    async def _run() -> dict[str, Any]:
        async with background_session() as session:
            stats = await UserAccessLogService(session).get_stats()
            return {"total": stats.total_count}

    result: dict[str, Any] = run_async(_run())
    return result
