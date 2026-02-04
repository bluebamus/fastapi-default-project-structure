"""
애플리케이션 설정 모듈

환경변수 기반의 설정을 Pydantic Settings로 관리합니다.

사용 방법:
    from config import app_settings, db_settings

    print(app_settings.DEBUG)
    print(db_settings.MYSQL_URL)

환경변수 우선순위:
    1. 시스템 환경변수
    2. .env 파일
    3. Field의 default 값
"""

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# =============================================================================
# 타임존 설정
# =============================================================================
class TimezoneSettings(BaseSettings):
    """
    타임존 설정

    애플리케이션 전역 타임존을 관리합니다.
    로그 시간, 데이터 생성 시간 등에 적용됩니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 타임존 문자열 (예: Asia/Seoul, UTC, America/New_York)
    TIME_ZONE: str = Field(
        default="Asia/Seoul",
        description="애플리케이션 전역 타임존",
    )

    @property
    def tz(self) -> ZoneInfo:
        """ZoneInfo 객체 반환"""
        return ZoneInfo(self.TIME_ZONE)

    def now(self) -> datetime:
        """현재 시간을 설정된 타임존으로 반환"""
        return datetime.now(self.tz)

    def localize(self, dt: datetime) -> datetime:
        """naive datetime을 설정된 타임존으로 변환"""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=self.tz)
        return dt.astimezone(self.tz)


# =============================================================================
# API 설명 (Scalar 문서에 표시)
# =============================================================================
API_DESCRIPTION = """
## FastAPI Default Project Structure

Repository 패턴과 Unit of Work 패턴을 적용한 FastAPI 프로젝트 템플릿입니다.

### 주요 기능

- **접속 로그 수집**: 모든 API 요청에 대한 접속 로그 자동 수집
- **사용자 정보 파싱**: User-Agent 기반 OS, 브라우저, 장치 정보 분석
- **통계 API**: 장치 유형, OS, 브라우저별 접속 통계

### 아키텍처

```
Router → Service → Repository → Database
           ↑
      UnitOfWork (트랜잭션 관리)
```

### 기술 스택

- **FastAPI**: 고성능 비동기 웹 프레임워크
- **SQLAlchemy 2.0**: 비동기 ORM (aiomysql)
- **Pydantic v2**: 데이터 검증 및 설정 관리
- **Scalar**: API 문서 UI

### 환경 설정

| 설정 | 설명 |
|------|------|
| `DEBUG=true` | 개발 모드 (DEBUG 로그, 테이블 자동 생성) |
| `DEBUG=false` | 운영 모드 (INFO 로그, Alembic 마이그레이션 사용) |
"""


# =============================================================================
# 기본 설정
# =============================================================================
class AppSettings(BaseSettings):
    """
    애플리케이션 기본 설정

    프로젝트 메타데이터와 전역 동작 모드를 관리합니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 프로젝트 이름 (Scalar 문서 제목, 관리자 페이지 제목)
    PROJECT_NAME: str = Field(
        default="FastAPI Project",
        description="프로젝트 이름",
    )

    # 애플리케이션 버전 (헬스체크 응답에 포함)
    VERSION: str = Field(
        default="0.1.0",
        description="애플리케이션 버전",
    )

    # API 문서 설명 (Scalar에 표시)
    DESCRIPTION: str = Field(
        default=API_DESCRIPTION,
        description="API 문서 설명",
    )

    # 디버그 모드
    # True: DEBUG 로그, 테이블 자동 생성, uvicorn reload, /docs 활성화
    # False: INFO 로그, Alembic 마이그레이션, /docs 비활성화
    DEBUG: bool = Field(
        default=True,
        description="디버그 모드 활성화",
    )

    # 관리자 페이지 활성화 (DEBUG와 독립적으로 동작)
    # True: /admin 접근 가능
    # False: /admin 접근 차단
    ADMIN: bool = Field(
        default=True,
        description="관리자 페이지 활성화",
    )

    # 실행 환경 (헬스체크 응답에 포함)
    ENV: Literal["development", "staging", "production"] = Field(
        default="development",
        description="실행 환경",
    )


# =============================================================================
# 데이터베이스 설정
# =============================================================================
class DatabaseSettings(BaseSettings):
    """
    데이터베이스 연결 설정

    MySQL 비동기 연결을 위한 aiomysql 드라이버를 사용합니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MySQL 서버 호스트 (IP 또는 도메인)
    MYSQL_HOST: str = Field(
        default="localhost",
        description="MySQL 서버 호스트",
    )

    # MySQL 서버 포트
    MYSQL_PORT: int = Field(
        default=3306,
        description="MySQL 서버 포트",
    )

    # MySQL 접속 사용자명
    MYSQL_USER: str = Field(
        default="root",
        description="MySQL 사용자명",
    )

    # MySQL 접속 비밀번호
    MYSQL_PASSWORD: str = Field(
        default="",
        description="MySQL 비밀번호",
    )

    # 사용할 데이터베이스 이름
    MYSQL_DATABASE: str = Field(
        default="fastapi_db",
        description="데이터베이스 이름",
    )

    @property
    def MYSQL_URL(self) -> str:
        """SQLAlchemy 비동기 연결 URL (aiomysql 드라이버)"""
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )


# =============================================================================
# CORS 설정
# =============================================================================
class CORSSettings(BaseSettings):
    """
    CORS (Cross-Origin Resource Sharing) 설정

    프론트엔드와 백엔드가 다른 도메인에서 실행될 때 필요합니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 허용할 Origin 목록 (["*"]는 모든 Origin 허용)
    CORS_ALLOW_ORIGINS: list[str] = Field(
        default=["*"],
        description="허용할 Origin 목록",
    )

    # 자격 증명 허용 여부 (쿠키, Authorization 헤더)
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=True,
        description="자격 증명 허용 여부",
    )

    # 허용할 HTTP 메서드
    CORS_ALLOW_METHODS: list[str] = Field(
        default=["*"],
        description="허용할 HTTP 메서드",
    )

    # 허용할 HTTP 헤더
    CORS_ALLOW_HEADERS: list[str] = Field(
        default=["*"],
        description="허용할 HTTP 헤더",
    )

    # 브라우저에 노출할 응답 헤더
    CORS_EXPOSE_HEADERS: list[str] = Field(
        default=[],
        description="노출할 응답 헤더",
    )

    # Preflight 요청 캐시 시간 (초)
    CORS_MAX_AGE: int = Field(
        default=600,
        description="Preflight 캐시 시간(초)",
    )


# =============================================================================
# 로깅 설정
# =============================================================================
class LogSettings(BaseSettings):
    """
    로깅 설정

    콘솔 및 파일 로깅을 설정합니다.
    DEBUG 모드에 따라 로그 레벨이 자동 결정됩니다.

    로그 레벨:
        - DEBUG: 디버깅용 상세 정보
        - INFO: 일반 정보 메시지
        - WARNING: 경고 (작은 문제)
        - ERROR: 오류 (큰 문제)
        - CRITICAL: 심각한 문제
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === 출력 대상 설정 ===
    # 콘솔(stdout) 로그 출력 활성화
    LOG_CONSOLE_ENABLED: bool = Field(
        default=True,
        description="콘솔 로그 활성화",
    )

    # 파일 로그 출력 활성화
    LOG_FILE_ENABLED: bool = Field(
        default=True,
        description="파일 로그 활성화",
    )

    # === 로그 레벨 설정 ===
    # None이면 DEBUG 설정에 따라 자동 결정
    LOG_LEVEL: str | None = Field(
        default=None,
        description="전역 로그 레벨 (미설정 시 DEBUG 따라 자동 결정)",
    )

    # 콘솔 로그 레벨 (None이면 DEBUG 설정에 따라 자동 결정)
    LOG_CONSOLE_LEVEL: str | None = Field(
        default=None,
        description="콘솔 로그 레벨",
    )

    # 파일 로그 레벨
    LOG_FILE_LEVEL: str = Field(
        default="INFO",
        description="파일 로그 레벨",
    )

    # === 파일 설정 ===
    # 로그 파일 저장 디렉토리
    LOG_DIR: str = Field(
        default="logs",
        description="로그 디렉토리 경로",
    )

    # 앱 로그 파일명 패턴 ({date}는 YYYY-MM-DD로 치환)
    LOG_APP_FILENAME: str = Field(
        default="{date}_app.log",
        description="앱 로그 파일명 패턴",
    )

    # 에러 로그 파일명 패턴 ({date}는 YYYY-MM-DD로 치환)
    LOG_ERROR_FILENAME: str = Field(
        default="{date}_error.log",
        description="에러 로그 파일명 패턴",
    )

    # 단일 로그 파일 최대 크기 (MB)
    LOG_MAX_SIZE_MB: int = Field(
        default=10,
        description="로그 파일 최대 크기(MB)",
    )

    # 보관할 백업 로그 파일 개수
    LOG_BACKUP_COUNT: int = Field(
        default=5,
        description="백업 로그 파일 개수",
    )

    # === 포맷 설정 ===
    # 콘솔 로그 출력 형식
    LOG_CONSOLE_FORMAT: str = Field(
        default="[{asctime}] {levelname:8} [{name}:{funcName}:{lineno}] {message}",
        description="콘솔 로그 포맷",
    )

    # 파일 로그 출력 형식
    LOG_FILE_FORMAT: str = Field(
        default="[{asctime}] {levelname:8} [{name}:{funcName}:{lineno}] {message}",
        description="파일 로그 포맷",
    )

    # 날짜 출력 형식
    LOG_DATE_FORMAT: str = Field(
        default="%Y-%m-%d %H:%M:%S",
        description="날짜 포맷",
    )

    def get_log_dir(self) -> Path:
        """로그 디렉토리 경로 반환 (없으면 생성)"""
        log_dir = Path(self.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def get_effective_log_level(self, debug: bool) -> str:
        """
        실제 적용할 로그 레벨 반환

        LOG_LEVEL이 설정되면 해당 값 사용,
        미설정 시 debug=True면 DEBUG, False면 INFO
        """
        if self.LOG_LEVEL is not None:
            return self.LOG_LEVEL
        return "DEBUG" if debug else "INFO"

    def get_effective_console_level(self, debug: bool) -> str:
        """
        실제 적용할 콘솔 로그 레벨 반환

        LOG_CONSOLE_LEVEL이 설정되면 해당 값 사용,
        미설정 시 debug=True면 DEBUG, False면 INFO
        """
        if self.LOG_CONSOLE_LEVEL is not None:
            return self.LOG_CONSOLE_LEVEL
        return "DEBUG" if debug else "INFO"


# =============================================================================
# 미들웨어 설정
# =============================================================================
class MiddlewareSettings(BaseSettings):
    """
    미들웨어 설정

    접속 로그 수집 등 미들웨어 관련 설정을 관리합니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 접속 로그 수집 활성화
    ACCESS_LOG_ENABLED: bool = Field(
        default=True,
        description="접속 로그 수집 활성화",
    )

    # 접속 로그 수집 제외 경로
    ACCESS_LOG_EXCLUDE_PATHS: list[str] = Field(
        default=["/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico"],
        description="로그 수집 제외 경로",
    )

    # 접속 로그 수집 제외 확장자
    ACCESS_LOG_EXCLUDE_EXTENSIONS: list[str] = Field(
        default=[".css", ".js", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg"],
        description="로그 수집 제외 확장자",
    )


# =============================================================================
# Redis 설정
# =============================================================================
class RedisSettings(BaseSettings):
    """
    Redis 연결 설정

    캐시, 세션, 메시지 큐 등에 사용됩니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Redis 서버 호스트
    REDIS_HOST: str = Field(
        default="localhost",
        description="Redis 서버 호스트",
    )

    # Redis 서버 포트
    REDIS_PORT: int = Field(
        default=6379,
        description="Redis 서버 포트",
    )

    # Redis 데이터베이스 번호 (0-15)
    REDIS_DB: int = Field(
        default=0,
        description="Redis 데이터베이스 번호",
    )

    # Redis 비밀번호 (None이면 인증 없이 접속)
    REDIS_PASSWORD: str | None = Field(
        default=None,
        description="Redis 비밀번호",
    )

    @property
    def REDIS_URL(self) -> str:
        """Redis 연결 URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# =============================================================================
# 설정 인스턴스 팩토리 (싱글톤)
# =============================================================================
@lru_cache
def get_timezone_settings() -> TimezoneSettings:
    """타임존 설정 인스턴스 반환 (캐싱)"""
    return TimezoneSettings()


@lru_cache
def get_app_settings() -> AppSettings:
    """앱 설정 인스턴스 반환 (캐싱)"""
    return AppSettings()


@lru_cache
def get_db_settings() -> DatabaseSettings:
    """DB 설정 인스턴스 반환 (캐싱)"""
    return DatabaseSettings()


@lru_cache
def get_cors_settings() -> CORSSettings:
    """CORS 설정 인스턴스 반환 (캐싱)"""
    return CORSSettings()


@lru_cache
def get_log_settings() -> LogSettings:
    """로그 설정 인스턴스 반환 (캐싱)"""
    return LogSettings()


@lru_cache
def get_redis_settings() -> RedisSettings:
    """Redis 설정 인스턴스 반환 (캐싱)"""
    return RedisSettings()


@lru_cache
def get_middleware_settings() -> MiddlewareSettings:
    """미들웨어 설정 인스턴스 반환 (캐싱)"""
    return MiddlewareSettings()


# =============================================================================
# 편의를 위한 전역 설정 인스턴스
# =============================================================================
# 모듈 import 시 바로 사용 가능한 설정 인스턴스
# 예: from config import app_settings
timezone_settings = get_timezone_settings()
app_settings = get_app_settings()
db_settings = get_db_settings()
cors_settings = get_cors_settings()
log_settings = get_log_settings()
redis_settings = get_redis_settings()
middleware_settings = get_middleware_settings()
