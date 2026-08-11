"""Reply 기능 의존성 (인터페이스 집합체).

services 의 기능 클래스를 session 으로 생성·결합하여 view 에 제공한다.
커밋은 **핸들러 본문**이 `await service.commit()` 으로 수행한다(P1-3).
예외 시에는 get_session 의 teardown 이 롤백을 수행한다.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_session, get_session
from app.features.reply.services.reply_service import ReplyService


async def get_reply_service(
    session: AsyncSession = Depends(get_session),
) -> ReplyService:
    """ReplyService 를 구성해 view 에 제공한다(쓰기용 — 커밋은 핸들러가 한다).

    이전에는 `yield` 이후 커밋했으나, FastAPI 상위 버전에서 yield dependency 의
    종료 코드가 **응답 전송 후에** 실행되도록 바뀌어 커밋 실패가 201 로 둔갑했다.
    커밋을 핸들러 본문으로 옮겨 응답 생성 전에 끝나도록 보장한다.
    """
    return ReplyService(session)


async def get_reply_service_readonly(
    session: AsyncSession = Depends(get_read_session),
) -> ReplyService:
    """조회 엔드포인트용 — 커밋하지 않는다.

    쓰기용 의존성을 읽기에 재사용하면 조회마다 불필요한 COMMIT 왕복이 생기고,
    인증 등 다른 의존성과 함께 쓸 때 한 세션에 커밋 주체가 둘이 되는 위험이 있다
    (auth 의 get_current_user 가 같은 이유로 분리되어 있다).
    """
    return ReplyService(session)
