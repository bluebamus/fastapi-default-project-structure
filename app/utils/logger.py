"""
FastAPI용 로깅 모듈

Django 로거 구조를 참고하여 FastAPI에 최적화된 로깅 시스템.

DEBUG 모드에 따른 로그 레벨:
    - DEBUG=True (기본값): DEBUG 레벨 로그 출력
    - DEBUG=False: INFO 레벨 로그만 출력

사용 예시:
    from app.utils.logger import get_logger

    logger = get_logger("song")
    logger.info("노래 생성 완료")
    logger.error("오류 발생", exc_info=True)

로그 레벨:
    1. DEBUG: 디버깅 목적
    2. INFO: 일반 정보
    3. WARNING: 경고 정보 (작은 문제)
    4. ERROR: 오류 정보 (큰 문제)
    5. CRITICAL: 아주 심각한 문제
"""

import logging
import sys
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from typing import Literal

from config import app_settings, log_settings, timezone_settings

# 로그 디렉토리 설정 (config.py의 LogSettings에서 관리)
LOG_DIR = log_settings.get_log_dir()

# 로그 레벨 타입
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class LoggerConfig:
    """
    로거 설정 클래스

    DEBUG 모드에 따라 로그 레벨이 자동으로 결정됩니다.
    - DEBUG=True: DEBUG 레벨 출력
    - DEBUG=False: INFO 레벨만 출력

    Note:
        LOG_LEVEL, LOG_CONSOLE_LEVEL이 명시적으로 .env에 설정된 경우
        해당 설정이 우선 적용됩니다.
    """

    # 출력 대상 설정 (LogSettings에서 가져옴)
    CONSOLE_ENABLED: bool = log_settings.LOG_CONSOLE_ENABLED
    FILE_ENABLED: bool = log_settings.LOG_FILE_ENABLED

    # 기본 설정 (DEBUG 모드에 따라 자동 결정)
    DEFAULT_LEVEL: str = log_settings.get_effective_log_level(app_settings.DEBUG)
    CONSOLE_LEVEL: str = log_settings.get_effective_console_level(app_settings.DEBUG)
    FILE_LEVEL: str = log_settings.LOG_FILE_LEVEL
    MAX_BYTES: int = log_settings.LOG_MAX_SIZE_MB * 1024 * 1024
    BACKUP_COUNT: int = log_settings.LOG_BACKUP_COUNT
    ENCODING: str = "utf-8"

    # 포맷 설정 (LogSettings에서 가져옴)
    CONSOLE_FORMAT: str = log_settings.LOG_CONSOLE_FORMAT
    FILE_FORMAT: str = log_settings.LOG_FILE_FORMAT
    DATE_FORMAT: str = log_settings.LOG_DATE_FORMAT

    # 파일명 패턴 (LogSettings에서 가져옴)
    APP_FILENAME: str = log_settings.LOG_APP_FILENAME
    ERROR_FILENAME: str = log_settings.LOG_ERROR_FILENAME


def _create_console_handler() -> logging.StreamHandler:
    """콘솔 핸들러 생성"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, LoggerConfig.CONSOLE_LEVEL))
    formatter = logging.Formatter(
        fmt=LoggerConfig.CONSOLE_FORMAT,
        datefmt=LoggerConfig.DATE_FORMAT,
        style="{",
    )
    handler.setFormatter(formatter)
    return handler


# =============================================================================
# 공유 파일 핸들러 (싱글톤)
# 모든 로거가 동일한 파일 핸들러를 공유하여 하나의 로그 파일에 기록
# =============================================================================
_shared_file_handler: RotatingFileHandler | None = None
_shared_error_handler: RotatingFileHandler | None = None


def _get_shared_file_handler() -> RotatingFileHandler:
    """
    공유 파일 핸들러 반환 (싱글톤)

    모든 로거가 하나의 기본 로그 파일(app.log)에 기록합니다.
    파일명 패턴은 LOG_APP_FILENAME 설정으로 변경 가능합니다.
    기본값: logs/{date}_app.log
    """
    global _shared_file_handler

    if _shared_file_handler is None:
        today = timezone_settings.now().strftime("%Y-%m-%d")
        filename = LoggerConfig.APP_FILENAME.format(date=today)
        log_file = LOG_DIR / filename

        _shared_file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=LoggerConfig.MAX_BYTES,
            backupCount=LoggerConfig.BACKUP_COUNT,
            encoding=LoggerConfig.ENCODING,
        )
        _shared_file_handler.setLevel(getattr(logging, LoggerConfig.FILE_LEVEL))
        formatter = logging.Formatter(
            fmt=LoggerConfig.FILE_FORMAT,
            datefmt=LoggerConfig.DATE_FORMAT,
            style="{",
        )
        _shared_file_handler.setFormatter(formatter)

    return _shared_file_handler


def _get_shared_error_handler() -> RotatingFileHandler:
    """
    공유 에러 파일 핸들러 반환 (싱글톤)

    모든 로거의 ERROR 이상 로그가 하나의 에러 로그 파일(error.log)에 기록됩니다.
    파일명 패턴은 LOG_ERROR_FILENAME 설정으로 변경 가능합니다.
    기본값: logs/{date}_error.log
    """
    global _shared_error_handler

    if _shared_error_handler is None:
        today = timezone_settings.now().strftime("%Y-%m-%d")
        filename = LoggerConfig.ERROR_FILENAME.format(date=today)
        log_file = LOG_DIR / filename

        _shared_error_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=LoggerConfig.MAX_BYTES,
            backupCount=LoggerConfig.BACKUP_COUNT,
            encoding=LoggerConfig.ENCODING,
        )
        _shared_error_handler.setLevel(logging.ERROR)
        formatter = logging.Formatter(
            fmt=LoggerConfig.FILE_FORMAT,
            datefmt=LoggerConfig.DATE_FORMAT,
            style="{",
        )
        _shared_error_handler.setFormatter(formatter)

    return _shared_error_handler


@lru_cache(maxsize=32)
def get_logger(name: str = "app") -> logging.Logger:
    """
    로거 인스턴스 반환 (캐싱 적용)

    Args:
        name: 로거 이름 (모듈명 권장: "song", "lyric", "video" 등)

    Returns:
        설정된 로거 인스턴스

    Example:
        logger = get_logger("song")
        logger.info("노래 처리 시작")
    """
    logger = logging.getLogger(name)

    # 이미 핸들러가 설정된 경우 반환
    if logger.handlers:
        return logger

    # 로그 레벨 설정
    logger.setLevel(getattr(logging, LoggerConfig.DEFAULT_LEVEL))

    # 핸들러 추가 (설정에 따라 선택적으로 추가)
    if LoggerConfig.CONSOLE_ENABLED:
        logger.addHandler(_create_console_handler())

    if LoggerConfig.FILE_ENABLED:
        logger.addHandler(_get_shared_file_handler())
        logger.addHandler(_get_shared_error_handler())

    # 상위 로거로 전파 방지 (중복 출력 방지)
    logger.propagate = False

    return logger


def setup_uvicorn_logging() -> dict:
    """
    Uvicorn 서버의 로깅 설정을 반환합니다.

    ============================================================
    언제 사용하는가?
    ============================================================
    Uvicorn 서버를 Python 코드로 직접 실행할 때 사용합니다.
    CLI 명령어(uvicorn main:app --reload)로 실행할 때는 적용되지 않습니다.

    ============================================================
    사용 방법
    ============================================================
    1. Python 코드에서 uvicorn.run() 호출 시:

        # run.py 또는 main.py 하단
        import uvicorn
        from app.utils.logger import setup_uvicorn_logging

        if __name__ == "__main__":
            uvicorn.run(
                "main:app",
                host="0.0.0.0",
                port=8000,
                reload=True,
                log_config=setup_uvicorn_logging(),  # 여기서 적용
            )

    2. 실행:
        python run.py
        또는
        python main.py

    ============================================================
    어떤 동작을 하는가?
    ============================================================
    Uvicorn의 기본 로깅 형식을 애플리케이션의 LogSettings와 일치시킵니다.

    - formatters: 로그 출력 형식 정의
        - default: 일반 로그용 (서버 시작/종료, 에러 등)
        - access: HTTP 요청 로그용 (클라이언트 IP, 요청 경로, 상태 코드)

    - handlers: 로그 출력 대상 설정
        - stdout으로 콘솔에 출력

    - loggers: Uvicorn 내부 로거 설정
        - uvicorn: 메인 로거
        - uvicorn.error: 에러/시작/종료 로그
        - uvicorn.access: HTTP 요청 로그

    ============================================================
    출력 예시
    ============================================================
    적용 전 (Uvicorn 기본):
        INFO:     127.0.0.1:52341 - "GET /docs HTTP/1.1" 200 OK
        INFO:     Uvicorn running on http://0.0.0.0:8000

    적용 후:
        [2026-01-14 15:30:00] INFO     [uvicorn.access] 127.0.0.1 - "GET /docs HTTP/1.1" 200
        [2026-01-14 15:30:00] INFO     [uvicorn:startup:45] Uvicorn running on http://0.0.0.0:8000

    ============================================================
    반환값 구조 (Python logging.config.dictConfig 형식)
    ============================================================
    {
        "version": 1,                      # dictConfig 버전 (항상 1)
        "disable_existing_loggers": False, # 기존 로거 유지
        "formatters": { ... },             # 포맷터 정의
        "handlers": { ... },               # 핸들러 정의
        "loggers": { ... },                # 로거 정의
    }

    Returns:
        dict: Uvicorn log_config 파라미터에 전달할 설정 딕셔너리
    """
    return {
        # --------------------------------------------------------
        # dictConfig 버전 (필수, 항상 1)
        # --------------------------------------------------------
        "version": 1,
        # --------------------------------------------------------
        # 기존 로거 비활성화 여부
        # False: 기존 로거 유지 (권장)
        # True: 기존 로거 모두 비활성화
        # --------------------------------------------------------
        "disable_existing_loggers": False,
        # --------------------------------------------------------
        # 포맷터 정의
        # 로그 메시지의 출력 형식을 지정합니다.
        # --------------------------------------------------------
        "formatters": {
            # 일반 로그용 포맷터 (서버 시작/종료, 에러 등)
            "default": {
                "format": LoggerConfig.CONSOLE_FORMAT,
                "datefmt": LoggerConfig.DATE_FORMAT,
                "style": "{",  # {변수명} 스타일 사용
            },
            # HTTP 요청 로그용 포맷터
            # 사용 가능한 변수: client_addr, request_line, status_code
            "access": {
                "format": '[{asctime}] {levelname:8} [{name}] {client_addr} - "{request_line}" {status_code}',
                "datefmt": LoggerConfig.DATE_FORMAT,
                "style": "{",
            },
        },
        # --------------------------------------------------------
        # 핸들러 정의
        # 로그를 어디에 출력할지 지정합니다.
        # --------------------------------------------------------
        "handlers": {
            # 일반 로그 핸들러 (stdout 출력)
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            # HTTP 요청 로그 핸들러 (stdout 출력)
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        # --------------------------------------------------------
        # 로거 정의
        # Uvicorn 내부에서 사용하는 로거들을 설정합니다.
        # DEBUG 모드에 따라 로그 레벨이 자동 결정됩니다.
        # --------------------------------------------------------
        "loggers": {
            # Uvicorn 메인 로거
            "uvicorn": {
                "handlers": ["default"],
                "level": LoggerConfig.DEFAULT_LEVEL,
                "propagate": False,  # 상위 로거로 전파 방지
            },
            # 에러/시작/종료 로그
            "uvicorn.error": {
                "handlers": ["default"],
                "level": LoggerConfig.DEFAULT_LEVEL,
                "propagate": False,
            },
            # HTTP 요청 로그 (GET /path HTTP/1.1 200 등)
            "uvicorn.access": {
                "handlers": ["access"],
                "level": LoggerConfig.DEFAULT_LEVEL,
                "propagate": False,
            },
        },
    }


# 편의를 위한 사전 정의된 로거 이름 상수
HOME_LOGGER = "home"
LYRIC_LOGGER = "lyric"
SONG_LOGGER = "song"
VIDEO_LOGGER = "video"
CELERY_LOGGER = "celery"
APP_LOGGER = "app"
