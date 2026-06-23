"""DEPRECATED 경로. app.core.db.session 으로 이전됨. Phase 8에서 제거 예정."""
from app.core.db.session import *          # noqa: F401,F403
from app.core.db.session import (          # noqa: F401
    engine, background_engine, AsyncSessionLocal, BackgroundSessionLocal,
    get_session, get_background_session, create_db_tables, dispose_engine,
)
from app.core.db.session import Base  # noqa: F401
