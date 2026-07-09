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

from pydantic import Field, model_validator
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
    ENV: Literal["development", "staging", "production", "test"] = Field(
        default="development",
        description="실행 환경",
    )

    # 개발용 `python main.py` 직접 실행 시 바인딩 호스트/포트.
    # 컨테이너·배포 환경에서 외부 접근을 허용하려면 0.0.0.0 이 기본이지만, 민감한
    # 환경에서는 SERVER_HOST=127.0.0.1 로 지정하고 리버스 프록시를 두는 것을 권장한다.
    SERVER_HOST: str = Field(
        default="0.0.0.0",  # nosec B104 - 컨테이너 실행 전제의 의도된 기본값(운영은 env 로 제한)
        description="개발 서버 바인딩 호스트",
    )

    # 개발 서버 바인딩 포트
    SERVER_PORT: int = Field(
        default=8000,
        description="개발 서버 바인딩 포트",
    )


# =============================================================================
# 데이터베이스 설정
# =============================================================================
def format_host(host: str) -> str:
    """DSN 에 넣을 호스트 표기를 만든다.

    IP(IPv4)·도메인은 그대로 두고, IPv6 만 대괄호로 감싼다. 감싸지 않으면 주소 안의
    콜론과 포트 구분자가 뒤섞여 ``@::1:3306`` 같은 깨진 DSN 이 만들어진다.
    """
    host = host.strip()
    if host.startswith("["):  # 이미 대괄호 표기
        return host
    return f"[{host}]" if ":" in host else host


def split_host_port(entry: str, default_port: int) -> tuple[str, int]:
    """``"host"`` / ``"host:port"`` 항목을 (호스트, 포트)로 분해한다.

    허용 형식:
        - IPv4      : ``10.0.0.11``            / ``10.0.0.11:3307``
        - 도메인    : ``replica.example.com``  / ``replica.example.com:3307``
        - IPv6      : ``[::1]``                / ``[2001:db8::10]:3307``

    IPv6 는 반드시 대괄호로 감싸야 한다. 감싸지 않으면 어디까지가 주소이고 어디부터가
    포트인지 구분할 수 없어 조용히 깨진 DSN 이 된다 — 그래서 여기서 명시적으로 거부한다.
    """
    entry = entry.strip()

    if entry.startswith("["):
        host, closing, rest = entry.partition("]")
        if not closing:
            raise ValueError(f"replica 호스트 '{entry}' 의 대괄호가 닫히지 않았습니다.")
        host = f"{host}]"
        if rest and not rest.startswith(":"):
            raise ValueError(f"replica 호스트 '{entry}' 형식이 잘못되었습니다 (기대: [주소]:포트).")
        port = rest[1:]
    else:
        if entry.count(":") > 1:
            raise ValueError(
                f"IPv6 주소 '{entry}' 는 대괄호로 감싸야 합니다 (예: [2001:db8::10]:3307)."
            )
        host, _, port = entry.partition(":")

    if not host or host == "[]":
        raise ValueError(f"replica 호스트가 비어 있습니다: '{entry}'")
    if port and not port.isdigit():
        raise ValueError(f"replica 호스트 '{entry}' 의 포트가 숫자가 아닙니다.")

    return host, int(port) if port else default_port


def mask_dsn(url: str) -> str:
    """DSN 의 비밀번호를 가린다 (로그·헬스체크 노출용).

    예: ``mysql+aiomysql://app:s3cr3t@db:3306/shop`` → ``mysql+aiomysql://app:***@db:3306/shop``
    """
    scheme, separator, rest = url.partition("://")
    if not separator or "@" not in rest:
        return url
    credentials, _, location = rest.rpartition("@")
    user, has_password, _ = credentials.partition(":")
    if not has_password:
        return url
    return f"{scheme}://{user}:***@{location}"


class DatabaseSettings(BaseSettings):
    """
    데이터베이스 연결 설정

    MySQL 비동기 연결을 위한 aiomysql 드라이버를 사용합니다.

    읽기/쓰기 분리(DB 라우터):
        DB_ROUTER_ENABLED=false  → 단일 서버. 모든 쿼리가 primary 로 간다(기본값).
        DB_ROUTER_ENABLED=true   → 라우터 활성. replica 가 없으면 여전히 primary 로 간다.
        + DB_REPLICATION_ENABLED=true
                                 → SELECT 는 replica, 쓰기는 primary 로 분리된다.

    라우팅 구현은 ``app/core/db/router.py`` 를 참고하세요.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === primary(쓰기) 서버 ===
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

    # === DB 라우터 (읽기/쓰기 분리) ===
    # 라우터 사용 여부. false 면 세션이 단일 엔진에 직접 바인딩된다(기존 동작).
    DB_ROUTER_ENABLED: bool = Field(
        default=False,
        description="DB 읽기/쓰기 라우터 활성화",
    )

    # 복제(replication) 사용 여부. true 면 SELECT 를 replica 로 보낸다.
    # DB_ROUTER_ENABLED=true 와 MYSQL_REPLICA_HOSTS 지정이 함께 필요하다.
    DB_REPLICATION_ENABLED: bool = Field(
        default=False,
        description="읽기 복제본(replica) 사용",
    )

    # 쓰기가 일어난 세션의 이후 SELECT 를 primary 로 고정할지 여부.
    # 복제 지연으로 방금 쓴 데이터가 replica 에서 안 보이는 것을 막는다(권장: true).
    DB_READ_STICKY_AFTER_WRITE: bool = Field(
        default=True,
        description="쓰기 이후 읽기를 primary 에 고정(read-after-write 일관성)",
    )

    # === replica(읽기) 서버 ===
    # replica 호스트 목록. "host" 또는 "host:port" 형식.
    # 예: ["replica-a", "replica-b:3307"]
    MYSQL_REPLICA_HOSTS: list[str] = Field(
        default=[],
        description="replica 호스트 목록 (host 또는 host:port)",
    )

    # 포트를 명시하지 않은 replica 에 적용할 기본 포트
    MYSQL_REPLICA_PORT: int = Field(
        default=3306,
        description="replica 기본 포트",
    )

    # replica 전용 자격증명. 미설정(None) 시 primary 값을 재사용한다.
    # 읽기 전용 계정을 분리해 두면 실수로 replica 에 쓰는 사고를 DB 권한 수준에서 막는다.
    MYSQL_REPLICA_USER: str | None = Field(
        default=None,
        description="replica 사용자명 (미설정 시 primary 재사용)",
    )

    MYSQL_REPLICA_PASSWORD: str | None = Field(
        default=None,
        description="replica 비밀번호 (미설정 시 primary 재사용)",
    )

    MYSQL_REPLICA_DATABASE: str | None = Field(
        default=None,
        description="replica 데이터베이스 이름 (미설정 시 primary 재사용)",
    )

    # === 마이그레이션 ===
    # Alembic 이 사용할 DSN 을 직접 지정한다 (로컬·CI 에서 SQLite 로 갈아끼울 때 유용).
    # 미설정 시 primary DSN 의 비동기 드라이버를 동기 드라이버로 바꿔 쓴다.
    ALEMBIC_DATABASE_URL: str | None = Field(
        default=None,
        description="Alembic 전용 DSN (미설정 시 primary DSN 에서 자동 유도)",
    )

    @property
    def ALEMBIC_URL(self) -> str:
        """Alembic 마이그레이션이 사용할 동기 DSN.

        Alembic 은 동기로 실행되므로 aiomysql(비동기 드라이버)을 쓸 수 없다.
        primary DSN 의 드라이버만 pymysql 로 바꿔서 같은 서버를 가리킨다.
        마이그레이션은 항상 primary 에서 실행한다 — replica 는 읽기 전용이다.
        """
        if self.ALEMBIC_DATABASE_URL:
            return self.ALEMBIC_DATABASE_URL
        return self.MYSQL_WRITER_URL.replace("+aiomysql", "+pymysql")

    @property
    def MYSQL_URL(self) -> str:
        """SQLAlchemy 비동기 연결 URL (aiomysql 드라이버) — primary(쓰기) 서버

        호스트는 IP·도메인 모두 가능하다 (IPv6 는 자동으로 대괄호 처리).
        """
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{format_host(self.MYSQL_HOST)}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    @property
    def MYSQL_WRITER_URL(self) -> str:
        """primary(쓰기) 서버 URL — ``MYSQL_URL`` 의 의미를 드러낸 별칭"""
        return self.MYSQL_URL

    @property
    def _replica_entries(self) -> list[str]:
        """공백을 정리한 유효 replica 항목만 추린다."""
        return [entry.strip() for entry in self.MYSQL_REPLICA_HOSTS if entry.strip()]

    @property
    def MYSQL_REPLICA_URLS(self) -> list[str]:
        """replica(읽기) 서버 URL 목록. 복제가 비활성이면 빈 목록."""
        if not self.replication_active:
            return []

        user = self.MYSQL_REPLICA_USER or self.MYSQL_USER
        password = self.MYSQL_REPLICA_PASSWORD or self.MYSQL_PASSWORD
        database = self.MYSQL_REPLICA_DATABASE or self.MYSQL_DATABASE

        urls = []
        for entry in self._replica_entries:
            host, port = split_host_port(entry, self.MYSQL_REPLICA_PORT)
            urls.append(f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}")
        return urls

    @property
    def replication_active(self) -> bool:
        """읽기/쓰기를 실제로 다른 서버로 보내는 상태인가."""
        return self.DB_ROUTER_ENABLED and self.DB_REPLICATION_ENABLED

    @property
    def routing_mode(self) -> Literal["single", "router-single", "router-replicated"]:
        """현재 라우팅 모드 (로그·헬스체크 표시용).

        - single:            라우터 미사용. 모든 쿼리 → primary
        - router-single:     라우터 사용, replica 없음. 모든 쿼리 → primary
        - router-replicated: 라우터 사용 + 복제. SELECT → replica / 쓰기 → primary
        """
        if not self.DB_ROUTER_ENABLED:
            return "single"
        return "router-replicated" if self.replication_active else "router-single"

    def describe_routing(self) -> dict[str, object]:
        """기동 시 로그로 남길 라우팅 구성 요약 (비밀번호는 마스킹)."""
        return {
            "mode": self.routing_mode,
            "router_enabled": self.DB_ROUTER_ENABLED,
            "replication_enabled": self.DB_REPLICATION_ENABLED,
            "sticky_after_write": self.DB_READ_STICKY_AFTER_WRITE,
            "writer": mask_dsn(self.MYSQL_WRITER_URL),
            "readers": [mask_dsn(url) for url in self.MYSQL_REPLICA_URLS],
        }

    @model_validator(mode="after")
    def _validate_routing(self) -> "DatabaseSettings":
        """모순된 라우팅 설정을 기동 시점에 차단한다(fail-fast).

        조용히 무시하면 '복제를 켰다고 믿는데 실제로는 primary 만 쓰는' 상태가
        운영에서 성능 문제로만 드러난다. 설정 단계에서 실패시키는 편이 안전하다.
        """
        if self.DB_REPLICATION_ENABLED and not self.DB_ROUTER_ENABLED:
            raise ValueError(
                "DB_REPLICATION_ENABLED=true 는 DB_ROUTER_ENABLED=true 를 필요로 합니다. "
                "라우터를 켜지 않으면 읽기/쓰기를 분리할 수 없습니다."
            )
        if self.DB_REPLICATION_ENABLED and not self._replica_entries:
            raise ValueError(
                "DB_REPLICATION_ENABLED=true 인데 MYSQL_REPLICA_HOSTS 가 비어 있습니다. "
                '읽기 복제본을 최소 1대 지정하세요 (예: MYSQL_REPLICA_HOSTS=["replica-a"]).'
            )

        # 호스트 표기 오류는 엔진 생성 시점의 난해한 예외가 아니라 여기서 잡는다.
        for entry in self._replica_entries:
            split_host_port(entry, self.MYSQL_REPLICA_PORT)

        return self


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
    # 주의: allow_origins=["*"]와 allow_credentials=True는 CORS 스펙상
    #       유효하지 않은 조합이다. credentials를 사용하려면 구체적인 Origin을 지정해야 한다.
    CORS_ALLOW_CREDENTIALS: bool = Field(
        default=False,
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

    @model_validator(mode="after")
    def _reject_wildcard_with_credentials(self) -> "CORSSettings":
        """`allow_origins=["*"]` 와 `allow_credentials=True` 조합을 거부한다.

        이 조합은 CORS 스펙상 무효일 뿐 아니라, Starlette 은 이때 요청 Origin 을 그대로
        반영해 '자격증명 포함 임의 출처 허용'이라는 취약 상태가 된다. 잘못된 운영 설정을
        기동 시점에 차단한다(fail-fast).
        """
        if self.CORS_ALLOW_CREDENTIALS and "*" in self.CORS_ALLOW_ORIGINS:
            raise ValueError(
                "CORS_ALLOW_CREDENTIALS=True 와 CORS_ALLOW_ORIGINS=['*'] 는 함께 쓸 수 없습니다. "
                "자격증명을 허용하려면 구체적인 Origin 을 지정하세요."
            )
        return self


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

    # 레이트 리밋(slowapi) 활성화
    RATE_LIMIT_ENABLED: bool = Field(
        default=True,
        description="요청 레이트 리밋 활성화",
    )

    # 라우트 데코레이터(@limiter.limit)용 기본 레이트 리밋 (slowapi 형식: "<count>/<period>")
    RATE_LIMIT_DEFAULT: str = Field(
        default="100/minute",
        description="라우트 데코레이터 기본 레이트 리밋",
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
# JWT 인증 설정
# =============================================================================
class JWTSettings(BaseSettings):
    """JWT 토큰(access/refresh) 설정.

    OAuth2 password flow 기반 인증에 사용됩니다.
    비밀 키는 운영 환경에서 반드시 안전한 값으로 교체하세요.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Access Token 서명 키
    ACCESS_TOKEN_SECRET_KEY: str = Field(
        default="change-this-access-token-secret-key",
        description="Access Token 서명 키",
    )
    # Refresh Token 서명 키 (access 와 다른 키 권장)
    REFRESH_TOKEN_SECRET_KEY: str = Field(
        default="change-this-refresh-token-secret-key",
        description="Refresh Token 서명 키",
    )
    # Access Token 만료 (분)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        description="Access Token 만료 시간(분)",
    )
    # Refresh Token 만료 (일)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        description="Refresh Token 만료 시간(일)",
    )
    # JWT 서명 알고리즘
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="JWT 서명 알고리즘",
    )


# =============================================================================
# API 설정
# =============================================================================
class ApiSettings(BaseSettings):
    """REST API 관련 설정."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # REST API 버전 (URL prefix 에 사용: /api/v1/...)
    API_VERSION: str = Field(
        default="v1",
        description="REST API 버전",
    )


# =============================================================================
# 세션 설정
# =============================================================================
class SessionSettings(BaseSettings):
    """세션 쿠키 설정.

    Note:
        현재 인증은 JWT(Bearer) 기반이라 세션 쿠키를 사용하는 코드는 없다.
        쿠키 세션을 도입할 때 이 설정을 주입하면 된다. 설정 자체는 `.env` 에
        있으므로 config 가 로드해 둔다(설정의 단일 출처 유지).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 세션 쿠키 이름
    SESSION_COOKIE_NAME: str = Field(
        default="session",
        description="세션 쿠키 이름",
    )

    # 세션 암호화 키 (운영 환경에서 반드시 교체)
    SESSION_SECRET_KEY: str = Field(
        default="change-this-session-secret-key",
        description="세션 암호화 키",
    )

    # 세션 만료 시간 (초, 기본값 24시간)
    SESSION_EXPIRE_SECONDS: int = Field(
        default=86400,
        description="세션 만료 시간(초)",
    )


# =============================================================================
# SMTP 이메일 설정
# =============================================================================
class SMTPSettings(BaseSettings):
    """이메일 발송(SMTP) 설정.

    Note:
        이메일 발송 모듈은 아직 없다. 설정만 config 에 로드해 두고, 발송 기능을
        구현할 때 `from config import smtp_settings` 로 가져다 쓴다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SMTP 서버 주소 (로컬 개발: localhost, Gmail: smtp.gmail.com)
    SMTP_SERVER: str = Field(
        default="localhost",
        description="SMTP 서버 주소",
    )

    # SMTP 서버 포트 (25: 비암호화, 587: TLS, 465: SSL)
    SMTP_PORT: int = Field(
        default=25,
        description="SMTP 서버 포트",
    )

    # SMTP 인증 사용자명 (보통 이메일 주소)
    SMTP_USERNAME: str = Field(
        default="",
        description="SMTP 사용자명",
    )

    # SMTP 인증 비밀번호 (Gmail 은 앱 비밀번호 사용)
    SMTP_PASSWORD: str = Field(
        default="",
        description="SMTP 비밀번호",
    )

    # 발신자 이메일 주소 (미설정 시 SMTP_USERNAME 사용)
    SMTP_FROM_EMAIL: str | None = Field(
        default=None,
        description="발신자 이메일 주소",
    )

    # 발신자 이름 (미설정 시 PROJECT_NAME 사용)
    SMTP_FROM_NAME: str | None = Field(
        default=None,
        description="발신자 이름",
    )

    # TLS 사용 여부 (포트 587)
    SMTP_TLS: bool = Field(
        default=False,
        description="TLS 사용 여부",
    )

    # SSL 사용 여부 (포트 465)
    SMTP_SSL: bool = Field(
        default=False,
        description="SSL 사용 여부",
    )

    @model_validator(mode="after")
    def _reject_tls_with_ssl(self) -> "SMTPSettings":
        """TLS 와 SSL 을 동시에 켜는 건 의미가 없다(포트별로 하나만 쓴다)."""
        if self.SMTP_TLS and self.SMTP_SSL:
            raise ValueError(
                "SMTP_TLS 와 SMTP_SSL 은 동시에 켤 수 없습니다. "
                "포트 587 이면 TLS, 465 면 SSL 하나만 사용하세요."
            )
        return self


# =============================================================================
# 이미지 업로드 설정
# =============================================================================
class UploadSettings(BaseSettings):
    """파일·이미지 업로드 설정.

    Note:
        업로드 핸들러는 아직 없다. 설정만 config 에 로드해 둔다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 업로드 파일 저장 경로 (프로젝트 루트 기준 상대 경로)
    UPLOAD_DIR: str = Field(
        default="uploads",
        description="업로드 파일 저장 경로",
    )

    # 업로드 이미지 최대 크기 (MB)
    UPLOAD_IMAGE_SIZE_LIMIT: int = Field(
        default=20,
        description="업로드 이미지 최대 크기(MB)",
    )

    # 업로드된 이미지 자동 리사이즈 활성화
    UPLOAD_IMAGE_RESIZE: bool = Field(
        default=False,
        description="이미지 자동 리사이즈 활성화",
    )

    # 리사이즈 최대 너비 (px, UPLOAD_IMAGE_RESIZE=true 시 적용)
    UPLOAD_IMAGE_RESIZE_WIDTH: int = Field(
        default=1200,
        description="리사이즈 최대 너비(px)",
    )

    # 리사이즈 최대 높이 (px, UPLOAD_IMAGE_RESIZE=true 시 적용)
    UPLOAD_IMAGE_RESIZE_HEIGHT: int = Field(
        default=2800,
        description="리사이즈 최대 높이(px)",
    )

    # 이미지 압축 품질 (0-100)
    UPLOAD_IMAGE_QUALITY: int = Field(
        default=85,
        ge=0,
        le=100,
        description="이미지 압축 품질(0-100)",
    )

    # 허용되는 이미지 확장자
    UPLOAD_ALLOWED_EXTENSIONS: list[str] = Field(
        default=[".jpg", ".jpeg", ".png", ".gif", ".webp"],
        description="허용 이미지 확장자",
    )


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


@lru_cache
def get_jwt_settings() -> JWTSettings:
    """JWT 설정 인스턴스 반환 (캐싱)"""
    return JWTSettings()


@lru_cache
def get_api_settings() -> ApiSettings:
    """API 설정 인스턴스 반환 (캐싱)"""
    return ApiSettings()


@lru_cache
def get_session_settings() -> SessionSettings:
    """세션 설정 인스턴스 반환 (캐싱)"""
    return SessionSettings()


@lru_cache
def get_smtp_settings() -> SMTPSettings:
    """SMTP 설정 인스턴스 반환 (캐싱)"""
    return SMTPSettings()


@lru_cache
def get_upload_settings() -> UploadSettings:
    """업로드 설정 인스턴스 반환 (캐싱)"""
    return UploadSettings()


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
jwt_settings = get_jwt_settings()
api_settings = get_api_settings()
session_settings = get_session_settings()
smtp_settings = get_smtp_settings()
upload_settings = get_upload_settings()
