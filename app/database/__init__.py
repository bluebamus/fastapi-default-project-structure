"""DEPRECATED 경로. app.core.db 로 이전됨. Phase 8에서 제거 예정."""
from app.core.db import *          # noqa: F401,F403
from app.core.db import session, unit_of_work, redis  # noqa: F401
