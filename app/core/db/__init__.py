"""
Database 모듈

데이터베이스 연결, 세션 관리, Unit of Work 패턴을 제공합니다.
"""

from app.core.db.session import (
    Base,
    engine,
    background_engine,
    AsyncSessionLocal,
    BackgroundSessionLocal,
    get_session,
    get_background_session,
    create_db_tables,
    dispose_engine,
)
from app.core.db.unit_of_work import BaseUnitOfWork

__all__ = [
    "Base",
    "engine",
    "background_engine",
    "AsyncSessionLocal",
    "BackgroundSessionLocal",
    "get_session",
    "get_background_session",
    "create_db_tables",
    "dispose_engine",
    "BaseUnitOfWork",
]
