"""User 기능 의존성 (인터페이스 집합체).

services 의 기능 클래스를 session 으로 생성·결합하여 view 에 제공한다.
커밋은 **핸들러 본문**이 `await service.commit()` 으로 수행한다(P1-3).
해시기·회전 저장소·관리 세션 저장소·소유권 정책은 core 의 provider 로 받는다 — auth 기능을 import 하지 않는다(C-2).
읽기 provider 도 같은 협력 객체로 조립한다(객체 생성뿐, Redis 왕복은 없다) — 클래스가 하나라 생성자도 하나다.
예외 시에는 get_writer_db_session 의 teardown 이 롤백을 수행한다.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.core.security.admin_session import AdminSessionStore
from app.core.security.authorization import OwnershipPolicy
from app.core.security.dependencies import (
    get_admin_session_store,
    get_ownership_policy,
    get_password_hasher,
    get_refresh_token_store,
)
from app.core.security.password_hasher import PasswordHasher
from app.core.security.refresh_store import RefreshTokenStore
from app.features.user.services.user_service import UserService


async def get_user_service(
    db_session: AsyncSession = Depends(get_writer_db_session),
    ownership: OwnershipPolicy = Depends(get_ownership_policy),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
    refresh_store: RefreshTokenStore = Depends(get_refresh_token_store),
    admin_sessions: AdminSessionStore | None = Depends(get_admin_session_store),
) -> UserService:
    """UserService 를 구성해 view 에 제공한다(쓰기용 — 커밋은 핸들러가 한다).

    이전에는 `yield` 이후 커밋했으나, FastAPI 상위 버전에서 yield dependency 의
    종료 코드가 **응답 전송 후에** 실행되도록 바뀌어 커밋 실패가 201 로 둔갑했다.
    커밋을 핸들러 본문으로 옮겨 응답 생성 전에 끝나도록 보장한다.
    """
    return UserService(db_session, ownership, password_hasher, refresh_store, admin_sessions)


async def get_user_service_readonly(
    db_session: AsyncSession = Depends(get_read_only_db_session),
    ownership: OwnershipPolicy = Depends(get_ownership_policy),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
    refresh_store: RefreshTokenStore = Depends(get_refresh_token_store),
    admin_sessions: AdminSessionStore | None = Depends(get_admin_session_store),
) -> UserService:
    """조회 엔드포인트용 — 커밋하지 않는다.

    쓰기용 의존성을 읽기에 재사용하면 조회마다 불필요한 COMMIT 왕복이 생기고,
    인증 등 다른 의존성과 함께 쓸 때 한 세션에 커밋 주체가 둘이 되는 위험이 있다
    (auth 의 get_current_user 가 같은 이유로 분리되어 있다).
    """
    return UserService(db_session, ownership, password_hasher, refresh_store, admin_sessions)
