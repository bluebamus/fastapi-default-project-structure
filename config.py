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

import logging
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

from dotenv import dotenv_values
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


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

    def utc_now(self) -> datetime:
        """현재 UTC 시각(aware). DB 에 저장하는 시각은 모두 여기서 만든다(service-hardening ADR-010).

        ``now()`` 는 로그·표시처럼 로컬 벽시계가 필요한 곳에만 쓴다.
        """
        return datetime.now(UTC)

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

Repository 패턴과 계층 분리를 적용한 FastAPI 백엔드 템플릿입니다.
기능 패키지가 공개한 `router` 를 `main.py` 가 명시적 `include_router` 로 취합합니다.

### 주요 기능

- **게시글·댓글·SNS·사용자 CRUD**, **JWT 인증**(OAuth2 password flow)
- **참조 예제**: `catalog`(ORM Repository), `reports`(Raw SQL Repository)
- **접속 로그 수집**: 요청마다 User-Agent 를 파싱해 background 세션으로 저장, 조회·통계 API 제공

### 아키텍처

```
View(Router) → Dependency → Service → Repository → AsyncSession
```

- 트랜잭션: 쓰기 핸들러 본문이 응답 DTO 를 검증한 뒤 `await service.commit()` 을 한 번 호출합니다
  (UnitOfWork 없음). 조회는 읽기 세션을 쓰고 커밋하지 않습니다.
- 오류 응답: `{"error_code", "message", "detail"}`

### 기술 스택

- **FastAPI**: 비동기 웹 프레임워크
- **SQLAlchemy 2.0**: 비동기 ORM (aiomysql)
- **Pydantic v2**: 데이터 검증 및 설정 관리
- **Redis**: startup 연결 검증, Celery broker/backend
- **Scalar**: API 문서 UI

### 환경 설정

| 설정 | 설명 |
|------|------|
| `DEBUG=true` | 개발 모드 (DEBUG 로그, 없는 테이블 생성, `/docs` 공개) |
| `DEBUG=false` | 운영 모드 (INFO 로그, 스키마는 Alembic, `/docs` 비공개) |
"""
# 관리 화면 설정은 여기(Scalar·/openapi.json 에 실리는 설명)에 적지 않는다 — ADMIN_DISABLED=true 일 때
# 앱이 내보내는 어떤 응답에도 관리 화면 경로가 나오지 않아야 한다(admin-login ADR-005).


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

    # API 문서 설명 (Scalar·/openapi.json 의 info.description). 미설정 시 API_DESCRIPTION
    DESCRIPTION: str = Field(
        default=API_DESCRIPTION,
        description="API 문서 설명",
    )

    # 디버그 모드
    # True: DEBUG 로그 기본값, 없는 테이블 생성, /docs 활성화, `python main.py` 의 reload,
    #       500 응답 detail 에 예외 문자열
    # False: INFO 로그 기본값, 테이블 생성 안 함(Alembic), /docs 비활성화
    DEBUG: bool = Field(
        default=True,
        description="디버그 모드 활성화",
    )

    # 관리 화면(SQLAdmin) 끄기 (DEBUG 와 독립적으로 동작) — admin-login ADR-005.
    # False(기본): /admin 마운트, **활성 슈퍼유저 로그인 필요**
    # True: 관리 화면을 완전히 끈다 — 마운트·sqladmin import·세션 미들웨어·인증 백엔드가 모두
    #       없고(/admin 이하 404), 앱의 어떤 응답·기동 로그에도 관리 화면 경로가 나오지 않는다.
    #       쓰지 않는 배포는 true 로 둔다(공격 표면 자체를 없앤다).
    #
    # 기본값이 "켜짐" 인 것은 의도다 — 개발을 우선 고려한 레퍼런스 구조라 받자마자 관리 화면으로
    # DB 를 들여다볼 수 있어야 한다(결정: 2026-08-12). 로그인 계정은 `scripts/create_superuser.py`
    # 로 만들고, 세션 쿠키(`admin_session`)는 아래 SESSION_SECRET_KEY 로 서명한다. 로그인하면
    # 게시글·댓글·사용자·접속로그의 조회·수정·삭제와 CSV 내보내기가 가능하다(비밀번호 해시만
    # SQLAdmin 설정으로 제외된다).
    #
    # 예전 이름 `ADMIN`(true=켬)은 없앴다. 환경 변수·`.env` 에 남아 있으면 조용히 무시하지 않고
    # 기동을 멈춘다(아래 `validate_no_legacy_admin`) — ADMIN=false 였다면 ADMIN_DISABLED=true.
    ADMIN_DISABLED: bool = Field(
        default=False,
        description="관리 화면 끄기 (true=마운트 없음·404). 기본 false=켬, 슈퍼유저 로그인 필요",
    )

    # 실행 환경 — 로그 출력 구성(시각 표기, staging/production 의 stderr 추가)에 쓴다.
    # 헬스체크 응답에는 들어가지 않는다(/health 는 status·version 만 반환).
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
def mysql_url(
    drivername: str, *, username: str, password: str, host: str, port: int, database: str
) -> URL:
    """MySQL 접속 URL 을 ``URL.create`` 로 만든다 (service-hardening ADR-004).

    문자열로 조립하면 비밀번호의 ``@ : / # % ?`` 가 구분자로 읽혀 접속 정보가 깨진다 —
    운영 비밀번호에서만 드러나는 실패다. ``URL`` 은 각 부분을 따로 들고 있다가 문자열로
    낼 때 필요한 만큼만 인코딩한다.

    호스트는 대괄호 없는 값으로 넣는다. IPv6(``::1``)는 ``URL`` 이 문자열로 낼 때 스스로
    ``[::1]`` 로 감싼다. 설정에 대괄호 표기(``[2001:db8::10]``)로 적어도 받아 준다.
    """
    host = host.strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return URL.create(
        drivername,
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    )


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
    def ALEMBIC_URL(self) -> URL:
        """Alembic 마이그레이션이 사용할 동기 URL.

        Alembic 은 동기로 실행되므로 aiomysql(비동기 드라이버)을 쓸 수 없다.
        primary URL 의 드라이버만 pymysql 로 바꿔서 같은 서버를 가리킨다.
        마이그레이션은 항상 primary 에서 실행한다 — replica 는 읽기 전용이다.
        """
        if self.ALEMBIC_DATABASE_URL:
            return make_url(self.ALEMBIC_DATABASE_URL)
        return self.MYSQL_WRITER_URL.set(drivername="mysql+pymysql")

    @property
    def MYSQL_URL(self) -> URL:
        """SQLAlchemy 비동기 연결 URL (aiomysql 드라이버) — primary(쓰기) 서버

        호스트는 IP·도메인 모두 가능하다 (IPv6 는 ``URL`` 이 대괄호로 감싼다).
        """
        return mysql_url(
            "mysql+aiomysql",
            username=self.MYSQL_USER,
            password=self.MYSQL_PASSWORD,
            host=self.MYSQL_HOST,
            port=self.MYSQL_PORT,
            database=self.MYSQL_DATABASE,
        )

    @property
    def MYSQL_WRITER_URL(self) -> URL:
        """primary(쓰기) 서버 URL — ``MYSQL_URL`` 의 의미를 드러낸 별칭"""
        return self.MYSQL_URL

    @property
    def _replica_entries(self) -> list[str]:
        """공백을 정리한 유효 replica 항목만 추린다."""
        return [entry.strip() for entry in self.MYSQL_REPLICA_HOSTS if entry.strip()]

    @property
    def MYSQL_REPLICA_URLS(self) -> list[URL]:
        """replica(읽기) 서버 URL 목록. 복제가 비활성이면 빈 목록."""
        if not self.replication_active:
            return []

        user = self.MYSQL_REPLICA_USER or self.MYSQL_USER
        password = self.MYSQL_REPLICA_PASSWORD or self.MYSQL_PASSWORD
        database = self.MYSQL_REPLICA_DATABASE or self.MYSQL_DATABASE

        urls = []
        for entry in self._replica_entries:
            host, port = split_host_port(entry, self.MYSQL_REPLICA_PORT)
            urls.append(
                mysql_url(
                    "mysql+aiomysql",
                    username=user,
                    password=password,
                    host=host,
                    port=port,
                    database=database,
                )
            )
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
            "writer": self.MYSQL_WRITER_URL.render_as_string(hide_password=True),
            "readers": [
                url.render_as_string(hide_password=True) for url in self.MYSQL_REPLICA_URLS
            ],
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

    출력은 stdout/stderr 로만 나가며 저장·rotation 은 컨테이너 런타임이나 운영
    agent 가 담당한다(NFR-009). 애플리케이션 파일 핸들러와 rotation 설정은
    제거됐다 — 요청 event loop 에서 동기 파일 write/flush 가 일어나지 않게 하려는
    것이다. 실제 쓰기는 QueueListener 스레드가 수행한다.

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
    # false 면 콘솔(stdout/stderr) 핸들러를 하나도 붙이지 않는다 — 앱 로거(listener 의 console·
    # error_console), ``uvicorn main:app`` CLI 의 uvicorn 핸들러, Celery worker 의 콘솔 핸들러 모두.
    # 판단은 app/utils/logs/config.py 의 console_enabled() 한 곳에서 한다. 파일 핸들러(Celery
    # --logfile)는 그대로 둔다. 앱에는 파일 출력이 없으므로 false 면 앱 로그는 버려지고, 기동 때
    # stderr 에 경고 한 줄을 남긴다.
    LOG_CONSOLE_ENABLED: bool = Field(
        default=True,
        description="콘솔(stdout/stderr) 로그 출력 — false 면 콘솔 핸들러를 붙이지 않는다",
    )

    # SQL 본문·바인딩 파라미터를 로그로 내보낼지 여부.
    #
    # 기본값이 False 인 것은 보안 요구다(NFR-001). DEBUG=true 면 유효 로그 레벨이
    # DEBUG 가 되고, 그 상태에서 SQLAlchemy 와 드라이버는 실행한 SQL 과 **바인딩된
    # 값**을 그대로 찍는다. 값에는 비밀번호 해시·토큰·검색어가 들어 있고 로그는
    # 보통 외부 collector 로 흘러간다. 쿼리를 눈으로 봐야 할 때만 명시적으로 켠다.
    LOG_SQL_ECHO_ENABLED: bool = Field(
        default=False,
        description="SQL 본문·파라미터 로그 출력 (기본 false — 민감정보 유출 방지)",
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

    # === 포맷 설정 ===
    # 콘솔 포매터(TzFormatter, style="{")의 fmt·datefmt. 기본값이 곧 확정 포맷(#3)이다:
    # [시간 TZ] LEVEL [app=..] [module:class:func:line] message
    # 쓸 수 있는 필드는 LogRecord 속성 + TzFormatter 가 채우는 {tzname}·{appname}·{classname}.
    # uvicorn CLI·Celery 의 콘솔 핸들러는 두 값 중 하나라도 **직접 지정했을 때만** 이 포맷으로
    # 바꾼다(기본이면 각 도구의 기본 출력 그대로). 비밀값 마스킹은 포맷과 무관하게 적용된다.
    LOG_CONSOLE_FORMAT: str = Field(
        default=(
            "[{asctime} {tzname}] {levelname:5} [app={appname}] "
            "[{module}:{classname}:{funcName}:{lineno}] {message}"
        ),
        description="콘솔 로그 포맷 (str.format 스타일 '{field}')",
    )

    # strftime 형식. development 에서는 그 뒤에 밀리초(.123)가 붙고, staging/production 은 UTC 로 렌더한다.
    LOG_DATE_FORMAT: str = Field(
        default="%Y-%m-%d %H:%M:%S",
        description="로그 시각 형식 (strftime)",
    )

    @field_validator("LOG_CONSOLE_FORMAT")
    @classmethod
    def _console_format_must_render(cls, value: str) -> str:
        """샘플 레코드를 실제로 한 번 포맷해 본다 — 모르는 필드·괄호 불일치·잘못된 서식을 기동 시 잡는다.

        TzFormatter 를 import 하면 순환(formatters → config)이라, 그것이 채우는 tzname·appname·
        classname 을 직접 넣은 표준 Formatter(같은 style="{")로 같은 검사를 한다.
        """
        record = logging.LogRecord("check", logging.INFO, __file__, 1, "msg", None, None, "check")
        record.tzname, record.appname, record.classname = "UTC", "app", "-"
        try:
            logging.Formatter(value, style="{").format(record)
        except Exception as exc:
            raise ValueError(f"로그 포맷을 적용할 수 없습니다: {exc}") from exc
        return value

    @field_validator("LOG_DATE_FORMAT")
    @classmethod
    def _date_format_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("빈 날짜 형식은 쓸 수 없습니다")
        return value

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

    # 앞단 신뢰 프록시 홉 수 (service-hardening ADR-006·ADR-021). **배포 전에 정한다.**
    # 0 이면 X-Forwarded-For·X-Real-IP 를 보지 않고 직접 피어 주소만 쓴다 — 헤더는
    # 클라이언트가 위조할 수 있다. 프록시 뒤 배포면 앞단 프록시 단 수로 설정한다:
    # 0 으로 두면 모든 클라이언트가 프록시 IP 하나로 보여 접속 로그와 로그인 레이트 리밋
    # (API·/admin)이 전체 사용자를 한 사람으로 취급하고, 실제보다 크게 잡으면 클라이언트가
    # 적은 헤더 값을 믿게 돼 IP 위조가 가능하다.
    TRUSTED_PROXY_HOPS: int = Field(
        default=0,
        ge=0,
        description=(
            "X-Forwarded-For 를 덧붙이는 신뢰 프록시 수(0=헤더 무시). 프록시 뒤 배포는 "
            "앞단 프록시 단 수로 — 0 이면 전원이 프록시 IP 하나, 크면 IP 위조"
        ),
    )

    # 접속 로그에 값을 남기지 않을 쿼리스트링 키(대소문자 무시) — 값은 `***` 로 저장한다.
    ACCESS_LOG_SENSITIVE_QUERY_KEYS: list[str] = Field(
        default=[
            "password",
            "token",
            "access_token",
            "refresh_token",
            "secret",
            "api_key",
            "code",
        ],
        description="접속 로그에서 값을 가릴 쿼리스트링 키",
    )

    # 접속 로그 보존 일수(security-ops-hardening ADR-002). Celery beat 가 하루 한 번 이보다 오래된 행을 지운다.
    # 0 이면 지우지 않는다. 음수는 기동 시 검증 오류.
    ACCESS_LOG_RETENTION_DAYS: int = Field(
        default=365,
        ge=0,
        description="접속 로그 보존 일수(0=삭제하지 않음). 기본 1년",
    )


# =============================================================================
# Redis 설정
# =============================================================================
class RedisSettings(BaseSettings):
    """
    Redis 연결 설정

    startup 의 필수 연결 확인(app/core/resources.py 의 ping)과 Celery broker/backend 에
    사용됩니다. 기능에 주입되는 공용 Redis 의존성(캐시·세션)은 아직 없습니다.
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
        """Redis 연결 URL (redis-py·Celery 가 문자열을 받는다).

        비밀번호는 퍼센트 인코딩한다 — ``@ : / # %`` 가 그대로 들어가면 URL 파싱이 깨진다
        (service-hardening ADR-004). redis-py 는 파싱할 때 다시 디코딩한다.
        """
        if self.REDIS_PASSWORD:
            password = quote(self.REDIS_PASSWORD, safe="")
            return f"redis://:{password}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# =============================================================================
# JWT 인증 설정
# =============================================================================
class JWTSettings(BaseSettings):
    """JWT 토큰(access/refresh)·인증 레이트 리밋 설정.

    OAuth2 password flow 기반 인증에 사용됩니다(``app/core/security/``, ``app/features/auth/``).
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
    # Access Token 만료 (분). access 는 서버에서 폐기할 수 없으므로 짧게 둔다 — 즉시 폐기의
    # 대안이 짧은 만료 + refresh 폐기다(service-hardening ADR-014).
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=15,
        gt=0,
        description="Access Token 만료 시간(분)",
    )
    # Refresh Token 만료 (일)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        gt=0,
        description="Refresh Token 만료 시간(일)",
    )
    # JWT 서명 알고리즘 — 대칭키(HMAC) 계열만 허용한다. 비밀 키 하나로 서명·검증하는 구성이라
    # 비대칭 알고리즘 이름이 들어오면 검증 경로가 어긋난다. `none` 은 물론 금지.
    JWT_ALGORITHM: Literal["HS256", "HS384", "HS512"] = Field(
        default="HS256",
        description="JWT 서명 알고리즘",
    )
    # 발급자(iss)·대상(aud). 검증 시 일치를 요구한다 — 같은 키를 쓰는 다른 서비스의 토큰이
    # 여기서 통과하지 않게 한다.
    JWT_ISSUER: str = Field(
        default="fastapi-default-project-structure",
        min_length=1,
        description="JWT 발급자(iss) — 검증 시 일치 필수",
    )
    JWT_AUDIENCE: str = Field(
        default="fastapi-default-project-structure-api",
        min_length=1,
        description="JWT 대상(aud) — 검증 시 일치 필수",
    )
    # exp·nbf·iat 검증에 허용하는 시계 오차(초). 서버 간 시계가 조금 어긋나도 막 발급한 토큰이
    # 거부되지 않게 한다.
    JWT_LEEWAY_SECONDS: int = Field(
        default=10,
        ge=0,
        description="JWT 시각 검증 허용 오차(초)",
    )

    # 레이트 리밋 (Redis 고정 창, service-hardening ADR-016·ADR-025)
    # 로그인: 같은 IP + 사용자명(소문자) 조합의 시도 수. 성공하면 이 카운터는 지운다.
    AUTH_LOGIN_MAX_ATTEMPTS: int = Field(
        default=5,
        gt=0,
        description="로그인 시도 허용 횟수(IP+사용자명, 창마다)",
    )
    AUTH_LOGIN_WINDOW_SECONDS: int = Field(
        default=60,
        gt=0,
        description="로그인 레이트 리밋 창(초) — IP+사용자명·IP 공통",
    )
    # 로그인: 같은 IP 의 전체 시도 수(사용자명을 바꿔 가며 시도하는 스터핑 대비).
    AUTH_LOGIN_IP_MAX_ATTEMPTS: int = Field(
        default=20,
        gt=0,
        description="로그인 시도 허용 횟수(IP, 창마다)",
    )
    # 회원가입: 같은 IP 의 시도 수.
    AUTH_REGISTER_MAX_ATTEMPTS: int = Field(
        default=5,
        gt=0,
        description="회원가입 시도 허용 횟수(IP, 창마다)",
    )
    AUTH_REGISTER_WINDOW_SECONDS: int = Field(
        default=3600,
        gt=0,
        description="회원가입 레이트 리밋 창(초)",
    )

    @property
    def access_token_ttl_seconds(self) -> int:
        """Access Token 유효 시간(초) — 응답의 ``expires_in``."""
        return self.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @property
    def refresh_token_ttl_seconds(self) -> int:
        """Refresh Token 유효 시간(초) — Redis 회전 기록·폐기 표시의 TTL."""
        return self.REFRESH_TOKEN_EXPIRE_DAYS * 86400


# =============================================================================
# 세션 설정
# =============================================================================
class SessionSettings(BaseSettings):
    """세션 쿠키 설정.

    Note:
        API 인증은 JWT(Bearer) 기반이다. 쿠키 세션은 ``/admin`` 로그인만 쓴다 — 관리 세션은
        Redis 서버 세션이고 쿠키(``admin_session``)에는 무작위 세션 ID 만 있다
        (``app/core/security/admin_session.py``, admin-session-hardening ADR-001). ``SESSION_SECRET_KEY``
        는 세션 ID 를 Redis 키로 바꾸는 HMAC 키다 — 바꾸면 모든 관리 세션이 무효가 된다.
        관리 세션 만료는 ``ADMIN_SESSION_*`` 가 정한다. ``SESSION_COOKIE_NAME`` 은 관리 화면
        쿠키에 쓰지 않고, 접속 로그 미들웨어가 ``session_id`` 로 기록할 쿠키 이름으로 읽는다.
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

    # 세션 키 (운영 환경에서 반드시 교체) — /admin 세션 ID 를 Redis 키로 바꾸는 HMAC 키.
    # 바꾸면 기존 관리자 세션이 모두 무효가 된다(다시 로그인).
    SESSION_SECRET_KEY: str = Field(
        default="change-this-session-secret-key",
        description="관리 세션 키 (/admin 세션 ID → Redis 키 HMAC)",
    )

    # 관리 세션 절대 만료(초) — 로그인 시각 기준, 요청해도 연장되지 않는다. 쿠키 Max-Age 도 이 값.
    ADMIN_SESSION_MAX_AGE_SECONDS: int = Field(
        default=28800,
        ge=60,
        description="관리 세션 절대 만료(초, 기본 8시간)",
    )

    # 관리 세션 미사용 만료(초) — 요청마다 다시 잰다. 절대 만료를 넘기지 않는다.
    ADMIN_SESSION_IDLE_SECONDS: int = Field(
        default=1800,
        ge=60,
        description="관리 세션 미사용 만료(초, 기본 30분)",
    )

    @model_validator(mode="after")
    def _idle_within_max_age(self) -> "SessionSettings":
        """미사용 만료가 절대 만료보다 길면 뜻이 없다(절대 만료가 먼저 온다)."""
        if self.ADMIN_SESSION_IDLE_SECONDS > self.ADMIN_SESSION_MAX_AGE_SECONDS:
            raise ValueError(
                "ADMIN_SESSION_IDLE_SECONDS 는 ADMIN_SESSION_MAX_AGE_SECONDS 이하여야 합니다."
            )
        return self


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
def get_session_settings() -> SessionSettings:
    """세션 설정 인스턴스 반환 (캐싱)"""
    return SessionSettings()


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
session_settings = get_session_settings()


# =============================================================================
# 설정 검사 (ADR-027 · ADR-028 · ADR-045)
# =============================================================================
# 값의 **출처**(.env 또는 환경 변수)와 **내용**(예시 값·약한 키·배포 금지 조합)을 import
# 시점에 본다. 잘못된 설정은 조용히 넘어가지 않고 기동 실패로 드러나야 한다 — 개발자는
# 오류 메시지를 보고 `.env` 를 고친다. test 는 검사하지 않는다(pytest 가 ENV=test 를 준다).
# SERVER_HOST 등 그 밖의 운영 조합은 여전히 막지 않는다(C-8).
DEPLOYED_ENVS = frozenset({"staging", "production"})

# 서명·세션 키의 최소 길이. `secrets.token_urlsafe(48)` 은 64자다.
SECRET_KEY_MIN_LENGTH = 32

# `.env` 파일이 없을 때 환경 변수로 **직접** 들어와야 하는 값. 컨테이너처럼 파일 없이
# 주입하는 배포는 이것들이 모두 있으면 통과한다. 하나라도 없으면 기본값으로 뜨게 되므로
# (예: ENV 가 없으면 development 로 간주돼 배포 검사가 꺼진다) 기동을 멈춘다.
REQUIRED_WITHOUT_ENV_FILE = (
    "ENV",
    "ACCESS_TOKEN_SECRET_KEY",
    "REFRESH_TOKEN_SECRET_KEY",
    "SESSION_SECRET_KEY",
    "MYSQL_HOST",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
)


def validate_env_source(
    env: str,
    env_file: Path = Path(".env"),
    environ: Mapping[str, str] = os.environ,
) -> None:
    """`.env` 가 없고 필수 값이 환경 변수로도 오지 않았으면 기동을 멈춘다 (ADR-045 ①).

    `env_file` 은 Settings 들의 ``env_file=".env"`` 와 같은 기준(작업 디렉터리)이다.
    메시지에는 빠진 설정 **이름**만 담는다.
    """
    if env == "test" or env_file.is_file():
        return
    missing = [name for name in REQUIRED_WITHOUT_ENV_FILE if name not in environ]
    if missing:
        raise RuntimeError(
            ".env 파일이 없고, 필수 설정이 환경 변수로도 주어지지 않았습니다: "
            + ", ".join(missing)
            + ". 로컬에서는 `cp .env.example .env` 후 값을 채우고, 배포에서는 환경 변수로 "
            "주입하세요."
        )


LEGACY_ADMIN_SETTING = "ADMIN"


def validate_no_legacy_admin(
    env: str,
    env_file: Path = Path(".env"),
    environ: Mapping[str, str] = os.environ,
) -> None:
    """예전 설정 `ADMIN` 이 환경 변수나 `.env` 에 남아 있으면 기동을 멈춘다 (admin-login ADR-005).

    `ADMIN`(true=켬)은 `ADMIN_DISABLED`(true=끔)로 바뀌었다. 뜻이 뒤집힌 이름이라 조용히 무시하면
    `ADMIN=false` 로 꺼 두었던 배포가 관리 화면이 **켜진 채** 뜬다. Settings 처럼 대소문자를 가리지
    않는다. test 는 검사하지 않는다(`validate_env_source` 와 같은 기준).
    """
    if env == "test":
        return
    sources = [name for name in environ if name.upper() == LEGACY_ADMIN_SETTING]
    if env_file.is_file():
        sources += [
            name
            for name in dotenv_values(env_file, encoding="utf-8")
            if name.upper() == LEGACY_ADMIN_SETTING
        ]
    if sources:
        raise RuntimeError(
            "설정 ADMIN 은 ADMIN_DISABLED 로 바뀌었습니다(뜻이 반대 — true 면 관리 화면을 끈다). "
            "환경 변수와 `.env` 에서 ADMIN 을 지우고, ADMIN=false 였다면 ADMIN_DISABLED=true 를, "
            "ADMIN=true 였다면 아무것도 넣지 않습니다(기본값이 켜짐)."
        )


def is_placeholder_secret(value: str) -> bool:
    """`.env.example` 류의 예시 값(교체하지 않은 비밀 키)인가."""
    v = value.strip().lower()
    return "change-this" in v or v.startswith("your-") or v == ""


def validate_deployment_safety(
    app: AppSettings | None = None,
    jwt: JWTSettings | None = None,
    session: SessionSettings | None = None,
    log: LogSettings | None = None,
    db: DatabaseSettings | None = None,
    redis: RedisSettings | None = None,
) -> None:
    """설정 내용을 검사해 위반을 모두 모아 RuntimeError 하나로 올린다.

    - test 를 뺀 **모든 ENV**: 예시 비밀 키·비밀번호, 짧은 키, access==refresh (ADR-045 ②).
      기본값·예시 값 그대로는 개발 환경에서도 오류다 — `.env` 를 채우라는 신호다.
    - staging/production 만: DEBUG, LOG_LEVEL=DEBUG(ADR-028). 켜진 관리 화면은 더 이상 막지 않는다 —
      ADR-045 ③ 의 확인 플래그는 관리 화면 로그인이 붙어 없앴다(admin-login ADR-004).

    메시지에는 설정 **이름**만 담는다(값 금지).
    """
    app = app or app_settings
    jwt = jwt or jwt_settings
    session = session or session_settings
    log = log or log_settings
    db = db or db_settings
    redis = redis or redis_settings
    if app.ENV == "test":
        return

    secrets = {
        "ACCESS_TOKEN_SECRET_KEY": jwt.ACCESS_TOKEN_SECRET_KEY,
        "REFRESH_TOKEN_SECRET_KEY": jwt.REFRESH_TOKEN_SECRET_KEY,
        "SESSION_SECRET_KEY": session.SESSION_SECRET_KEY,
        # DB 는 이 스켈레톤이 반드시 붙는 대상이라, 빈 비밀번호(=인증 없는 접속)도 위반이다.
        "MYSQL_PASSWORD": db.MYSQL_PASSWORD,
    }
    # Redis 는 **비어 있는 것이 정당한 구성**이다 — 인증 없는 사설망 Redis.
    # 그래서 비어 있으면 검사하지 않고, 값이 있을 때만 예시 값인지 본다.
    redis_password = redis.REDIS_PASSWORD or ""
    if redis_password.strip():
        secrets["REDIS_PASSWORD"] = redis_password
    violations = [
        f"{name} 가 예시 값(placeholder)입니다"
        for name, value in secrets.items()
        if is_placeholder_secret(value)
    ]
    for name in ("ACCESS_TOKEN_SECRET_KEY", "REFRESH_TOKEN_SECRET_KEY", "SESSION_SECRET_KEY"):
        value = secrets[name]
        if not is_placeholder_secret(value) and len(value.strip()) < SECRET_KEY_MIN_LENGTH:
            violations.append(f"{name} 가 {SECRET_KEY_MIN_LENGTH}자보다 짧습니다")
    if jwt.ACCESS_TOKEN_SECRET_KEY == jwt.REFRESH_TOKEN_SECRET_KEY:
        violations.append("ACCESS_TOKEN_SECRET_KEY 와 REFRESH_TOKEN_SECRET_KEY 가 같습니다")
    if app.ENV in DEPLOYED_ENVS:
        # debug 모드는 배포 환경에서 켜지면 안 된다 — 유효 로그 레벨이 DEBUG 가 되고,
        # 롤백 상세 로그가 실행된 SQL 과 바인딩된 값을 그대로 남긴다(NFR-001).
        if app.DEBUG:
            violations.append("DEBUG 가 켜져 있습니다")
        if (log.LOG_LEVEL or "").strip().upper() == "DEBUG":
            violations.append("LOG_LEVEL 이 디버그 레벨입니다")
        # 관리 화면을 켜 둔 배포는 막지 않는다 — 슈퍼유저 로그인이 필요하다(admin-login ADR-004).
    if violations:
        raise RuntimeError(
            f"ENV={app.ENV} 설정 검사 실패 — " + "; ".join(violations) + ". "
            "`.env`(또는 환경 변수)를 고치세요. 비밀 키는 "
            'uv run python -c "import secrets; print(secrets.token_urlsafe(48))" 로 키마다 따로 '
            "만들고, 비밀번호는 실제 값을 넣습니다(Redis 인증을 쓰지 않으면 비웁니다)."
        )


validate_env_source(app_settings.ENV)
validate_no_legacy_admin(app_settings.ENV)
validate_deployment_safety()
