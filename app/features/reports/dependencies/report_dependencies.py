"""Reports 기능 의존성.

세션 선택은 **데이터 접근 방식이 아니라 하는 일**이 정한다 — Raw SQL 이라고 해서
조회에 쓰기 세션을 쓰지 않고, 조회는 read-only 세션이다(TX-002). 스냅샷 적재처럼
실제로 쓰는 경로만 writer 세션을 받는다.

의존성은 **조립만** 한다. 커밋하지 않는다(C-2).
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.features.reports.services.report_service import ReportService


async def get_report_service_readonly(
    db_session: AsyncSession = Depends(get_read_only_db_session),
) -> ReportService:
    """조회용 — 커밋하지 않으며, 쓰기를 시도하면 즉시 실패한다."""
    return ReportService(db_session)


async def get_report_service(
    db_session: AsyncSession = Depends(get_writer_db_session),
) -> ReportService:
    """적재용 — writer 세션을 넘길 뿐, 커밋은 View 본문이 한다(TX-001)."""
    return ReportService(db_session)
