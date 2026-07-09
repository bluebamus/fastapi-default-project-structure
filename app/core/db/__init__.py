"""
Database 모듈

데이터베이스 연결과 세션 관리를 제공합니다.
요청 스코프 세션은 get_session(DI), 요청 밖 작업은 background_session(컨텍스트)을 사용한다.
(UnitOfWork 는 제거되었고 트랜잭션 경계는 의존성/컨텍스트가 담당한다.)

읽기/쓰기 분리는 DatabaseRouter 가 담당한다(app/core/db/router.py).
.env 의 DB_ROUTER_ENABLED / DB_REPLICATION_ENABLED 로 활성화한다.
"""

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    create_routing_sessionmaker,
    mark_read_only,
    using_writer,
)
from app.core.db.session import (
    AsyncSessionLocal,
    BackgroundSessionLocal,
    Base,
    background_engine,
    background_session,
    create_db_tables,
    db_router,
    dispose_engine,
    engine,
    get_background_session,
    get_read_session,
    get_session,
    get_write_session,
    read_engines,
    writer_engine,
)

__all__ = [
    "Base",
    "engine",
    "writer_engine",
    "read_engines",
    "background_engine",
    "db_router",
    "DatabaseRouter",
    "ReadOnlyRoutingError",
    "create_routing_sessionmaker",
    "using_writer",
    "mark_read_only",
    "AsyncSessionLocal",
    "BackgroundSessionLocal",
    "get_session",
    "get_read_session",
    "get_write_session",
    "get_background_session",
    "background_session",
    "create_db_tables",
    "dispose_engine",
]
