"""Reports 기능 의존성 — 조회 전용.

Raw SQL 이라는 이유로 쓰기 세션을 쓰지 않는다. 데이터 접근 방식이 무엇이든
조회는 read-only 세션이다(TX-002).
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session
from app.features.reports.services.report_service import ReportService


async def get_report_service_readonly(
    db_session: AsyncSession = Depends(get_read_only_db_session),
) -> ReportService:
    """조회용 — 커밋하지 않으며, 쓰기를 시도하면 즉시 실패한다."""
    return ReportService(db_session)
