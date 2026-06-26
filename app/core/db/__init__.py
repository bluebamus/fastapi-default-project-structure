"""
Database 모듈

데이터베이스 연결과 세션 관리를 제공합니다.
요청 스코프 세션은 get_session(DI), 요청 밖 작업은 background_session(컨텍스트)을 사용한다.
(UnitOfWork 는 제거되었고 트랜잭션 경계는 의존성/컨텍스트가 담당한다.)
"""

from app.core.db.session import (
    AsyncSessionLocal,
    BackgroundSessionLocal,
    Base,
    background_engine,
    background_session,
    create_db_tables,
    dispose_engine,
    engine,
    get_background_session,
    get_session,
)

__all__ = [
    "Base",
    "engine",
    "background_engine",
    "AsyncSessionLocal",
    "BackgroundSessionLocal",
    "get_session",
    "get_background_session",
    "background_session",
    "create_db_tables",
    "dispose_engine",
]
