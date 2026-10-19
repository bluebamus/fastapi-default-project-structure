"""Home 접속 로그 기능 의존성 (인터페이스 집합체).

home 은 조회 엔드포인트만 가진다(쓰기 없음). 접속 로그 적재는 미들웨어가
`background_db_session()` 으로 따로 처리하므로, 이 의존성은 커밋할 이유가 없다.

따라서 읽기 전용 세션을 쓴다 — 조회마다 발생하던 불필요한 COMMIT 왕복이 사라지고,
`DB_ROUTER_ENABLED` 가 켜지면 replica 로 라우팅된다. 읽기 핸들러가 몰래 쓰기를
시도하면 `ReadOnlyRoutingError` 로 즉시 실패한다.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session
from app.features.home.services.access_log_retention_service import AccessLogRetentionService
from app.features.home.services.user_access_log_service import UserAccessLogService
from config import middleware_settings, timezone_settings


def build_access_log_retention_service(db_session: AsyncSession) -> AccessLogRetentionService:
    """보존 정책 서비스를 설정값(``ACCESS_LOG_RETENTION_DAYS``)과 UTC 시계로 조립한다 — beat 태스크가 쓴다."""
    return AccessLogRetentionService(
        db_session,
        retention_days=middleware_settings.ACCESS_LOG_RETENTION_DAYS,
        clock=timezone_settings.utc_now,
    )


def build_user_access_log_service(db_session: AsyncSession) -> UserAccessLogService:
    """세션으로 UserAccessLogService 를 조립한다 — HTTP provider 와 Celery 태스크가 함께 쓴다.

    조립 규칙을 한 곳에 둔다(service-hardening ADR-012). 태스크는 요청 밖이라 ``Depends`` 를 쓸 수
    없으므로, 세션을 인자로 받는 일반 함수로 둔다.
    """
    return UserAccessLogService(db_session)


async def get_access_log_service(
    db_session: AsyncSession = Depends(get_read_only_db_session),
) -> UserAccessLogService:
    """UserAccessLogService 를 구성해 view 에 제공한다(읽기 전용 — 커밋하지 않는다)."""
    return build_user_access_log_service(db_session)
