"""앱 로깅 서브시스템 (app/utils/logs).

공개 API:
    from app.utils.logs import get_logger, LoggerMixin, configure_logging, setup_uvicorn_logging

- get_logger(name): 환경별 구성을 공유하는 로거.
- LoggerMixin: 클래스가 self.log 로 클래스명 자동 주입(방식 C).
- 비클래스 코드는 ContextFilter(방식 A)가 호출 프레임에서 클래스명을 자동 추출.
- 로그 헤더: [시간 TZ] LEVEL [app=..] [module:class:func:line] message
"""
from app.utils.logs.config import LOG_FORMAT
from app.utils.logs.filters import ContextFilter
from app.utils.logs.formatters import TzFormatter
from app.utils.logs.mixin import LoggerMixin
from app.utils.logs.setup import configure_logging, get_logger, setup_uvicorn_logging

__all__ = [
    "LOG_FORMAT",
    "ContextFilter",
    "TzFormatter",
    "LoggerMixin",
    "configure_logging",
    "get_logger",
    "setup_uvicorn_logging",
]
