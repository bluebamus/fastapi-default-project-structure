# FastAPI Default Project Structure

Repository 패턴과 계층 분리 아키텍처를 적용한 FastAPI 프로젝트 템플릿입니다.
표준 FastAPI 배선을 따릅니다: 각 도메인 앱 패키지(`app/domains/<name>/__init__.py`)가 하위 뷰 라우터를 취합한 `router` 를 공개하고, `main.py` 가 이를 `include_router` 로 최종 취합하며 앱 설정을 구성합니다.

## 목차

- [개요](#개요)
- [기술 스택](#기술-스택)
- [아키텍처](#아키텍처)
- [프로젝트 구조](#프로젝트-구조)
- [데이터 흐름](#데이터-흐름)
- [핵심 패턴](#핵심-패턴)
- [시작하기](#시작하기)
- [환경 설정](#환경-설정)
- [로깅 시스템](#로깅-시스템)
- [접속 로그 미들웨어](#접속-로그-미들웨어)
- [신규 모듈 개발 가이드](#신규-모듈-개발-가이드)
- [API 문서](#api-문서)

---

## 개요

이 프로젝트는 FastAPI 기반의 확장 가능한 백엔드 애플리케이션 템플릿입니다.

### 주요 특징

- **계층 분리 아키텍처**: Router → Service → Repository → Database
- **의존성 기반 트랜잭션 경계**: 기능 의존성(`get_<name>_service`)이 서비스 구성 + 커밋을 담당(UnitOfWork 미사용)
- **트랜잭션 관리**: 요청 성공 시 의존성이 커밋, 예외 시 세션 teardown이 롤백
- **N+1 문제 해결**: Eager Loading 전략 내장 (selectin, joined, subquery)
- **유연한 설정**: Pydantic Settings 기반 환경 변수 관리
- **구조화된 로깅**: 콘솔/파일 로그 분리, 자동 로그 로테이션
- **API 문서**: Scalar UI 기반 인터랙티브 문서
- **관리자 페이지**: SQLAdmin 통합

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| Framework | FastAPI 0.115+ |
| ORM | SQLAlchemy 2.0 (async) |
| Database | MySQL (aiomysql) |
| Validation | Pydantic v2 |
| Migration | Alembic |
| Cache | Redis |
| Admin | SQLAdmin |
| API Docs | Scalar |
| Task Queue | Celery + Redis |

---

## 아키텍처

### 3계층 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                        HTTP Request                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Router (API Layer)                        │
│  - 요청/응답 처리                                              │
│  - 입력 유효성 검사 (Pydantic)                                  │
│  - 의존성 주입 (Depends)                                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 Service (Business Logic)                     │
│  - 비즈니스 로직 처리                                          │
│  - 데이터 변환 및 검증                                         │
│  - 트랜잭션 조율                                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                Repository (Data Access)                      │
│  - 데이터베이스 CRUD                                          │
│  - 쿼리 캡슐화                                                │
│  - N+1 문제 해결                                              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Database (MySQL)                          │
└─────────────────────────────────────────────────────────────┘
```

### 요청 처리 & 트랜잭션 경계 (UnitOfWork 미사용)

```
Router(view) → Depends(get_<name>_service) → Service(session) → Repository → DB
```

트랜잭션 경계는 **기능 의존성**이 담당합니다. `get_<name>_service` 가 세션으로 Service를 구성해
뷰에 주입하고, 요청이 성공하면 `await session.commit()` 으로 커밋합니다(예외 시 `get_session`
teardown 이 롤백). 요청 밖(백그라운드/Celery)에서는 `background_session()` 컨텍스트(별도 풀)를
사용해 메인 API 풀 고갈을 방지합니다.

---

## 프로젝트 구조

> 상세한 아키텍처 설명은 **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** 를 참고하세요.

```
fastapi-default-project-structure/
├── main.py                      # 진입점: 각 앱 router 를 include_router 로 취합 + 앱 설정
├── config.py                    # 환경 설정 (Pydantic Settings)
├── pyproject.toml               # 의존성 및 도구 설정 ([tool.uv] package = false)
│
├── app/
│   ├── domains/                 # 기능 단위 앱 (__init__.py가 router 취합 → main.py APPS 에 등록)
│   │   └── <name>/              # 각 앱 디렉토리
│   │       ├── __init__.py      # router(+선택 admin_views) 공개
│   │       ├── api/routers/     # router.py + v1/ 엔드포인트
│   │       ├── models/          # SQLAlchemy ORM 모델
│   │       ├── schemas/         # Pydantic 스키마
│   │       ├── services/        # 비즈니스 로직
│   │       ├── repositories/    # 데이터 접근 계층
│   │       ├── dependencies/    # 기능 의존성 (서비스 구성 + 트랜잭션 경계)
│   │       ├── admin.py         # SQLAdmin 뷰 (선택)
│   │       └── tests/           # 테스트
│   │
│   ├── core/                    # 프레임워크 인프라 (도메인이 의존)
│   │   ├── exception.py         # 공통 예외 계층
│   │   ├── db/                  # 세션, 커넥션 풀, background_session, redis(스텁)
│   │   ├── models/              # SQLAlchemy Base
│   │   ├── repositories/        # BaseRepository (제네릭 CRUD)
│   │   ├── services/            # BaseService
│   │   └── middlewares/         # CORS, UserInfo, AccessLogSink
│   │
│   ├── celery/                  # 중앙 Celery 앱 + tasks.py + run_async 브릿지
│   ├── shared/pagination/       # 페이지네이션 헬퍼
│   └── utils/                   # logs(구조화 로깅), authenticator(스텁)
│
├── migrations/                  # Alembic (env.py가 각 앱 models import로 메타데이터 수집)
└── docs/
    ├── ARCHITECTURE.md          # 아키텍처 공식 문서 (SSOT)
    ├── concepts/                # 개념·패턴 심화 해설
    └── refactoring/             # 변경 기록
```

### 핵심 파일 설명

| 파일 | 설명 |
|------|------|
| `main.py` | FastAPI 조립 — 각 앱 `router` 를 `include_router(prefix="/api")` 로 취합 + 미들웨어/예외/문서/lifespan/Admin 설정 |
| `app/domains/<name>/__init__.py` | 하위 뷰 라우터를 취합한 `router` (및 선택 `admin_views`) 공개 — `main.py` 의 `APPS` 가 이를 취합 |
| `app/core/db/session.py` | SQLAlchemy 엔진, 세션 팩토리, 커넥션 풀, `background_session` |
| `app/domains/<name>/dependencies/` | 기능 의존성 — Service 구성 + 요청 성공 시 커밋(트랜잭션 경계) |
| `app/core/exception.py` | 커스텀 예외 계층 (4xx, 5xx, 비즈니스 예외) |
| `migrations/env.py` | 각 앱 `models` 모듈을 import 해 `Base.metadata` 수집 → Alembic autogenerate |

### `app/` 구현 규칙 (Conventions)

`app/` 아래는 **3개 영역**으로 나뉘며, 의존은 한 방향으로만 흐릅니다.

```
domains → core → shared
```

| 영역 | 역할 | 규칙 |
|------|------|------|
| `app/domains/<name>/` | 기능 단위 앱(도메인) | 비즈니스 코드는 전부 여기. `core`를 사용하고 다른 도메인은 import하지 않음 |
| `app/core/` | 프레임워크 인프라 (Base*, db, 미들웨어) | **절대 `domains`를 import하지 않음**. 도메인은 `core`의 Base 클래스를 상속 |
| `app/shared/`, `app/utils/` | 순수 유틸리티 (페이지네이션, 로깅) | 외부·상위 계층 의존 없음. 누구나 import 가능 |

> 핵심 규칙: **`core`는 도메인을 모른다.** 도메인이 `core`의 미들웨어 등에 자신을 연결해야 할 때는 직접 import가 아니라 등록 훅(예: `access_log_sink.register_sink()`)을 통한다.

#### 도메인 앱 표준 레이아웃

새 앱은 아래 구조와 **파일 네이밍 표준**을 따릅니다. (기준 구현체: `app/domains/home/`)

```
app/domains/<name>/
├── api/
│   └── routers/
│       ├── router.py          # 앱 루트 라우터 (v1/ 등을 묶음) — 필수
│       └── v1/<name>.py       # 버전별 엔드포인트 — 필수
├── models/models.py           # SQLAlchemy ORM 모델 — 필수
├── schemas/                   # Pydantic 요청/응답 스키마 — 필수
├── repositories/              # BaseRepository 확장 (데이터 접근) — 필수
├── services/                  # BaseService 확장 (비즈니스 로직) — 필수
├── dependencies/              # 기능 의존성 (Service 구성 + 트랜잭션 경계) — 필수
│   └── <name>_dependencies.py
├── tests/                     # pytest — 필수
├── exceptions.py              # 도메인 예외 — 선택
└── admin.py                   # SQLAdmin ModelView — 선택

# Celery 태스크는 도메인이 아니라 중앙 app/celery/tasks.py 에 정의한다.
```

**파일 네이밍 표준 (반드시 준수):**

| 용도 | 올바른 이름 | 쓰지 말 것 |
|------|------------|-----------|
| 도메인 예외 | `exceptions.py` | `<name>_exception.py` |
| FastAPI 의존성 | `dependencies.py` | `dependency.py` |
| SQLAdmin 뷰 | `admin.py` | `api/<name>_admin.py` |
| Celery 태스크 | 중앙 `app/celery/tasks.py` | 도메인별 `worker/` |
| 기능 의존성 | `dependencies/` 패키지 | 단일 `dependencies.py`도 허용 |

#### 계층별 책임과 호출 규칙

```
Router  →  Depends(get_<name>_service)  →  Service(session)  →  Repository  →  DB
 (API)         (트랜잭션 경계)              (비즈니스 로직)     (데이터 접근)
```

| 계층 | 하는 일 | 하지 말 것 |
|------|---------|-----------|
| **Router** | 입력 검증(Pydantic), `Depends(get_<name>_service)`로 Service 주입, Service 호출 → 응답 변환 | 직접 ORM 쿼리·트랜잭션 제어 |
| **Dependency** | `get_session`으로 세션 주입 → `Service(session)` 구성 → yield → 성공 시 `session.commit()` | 비즈니스 로직 |
| **Service** | `BaseService` 상속, `self.session`/Repository로 데이터 접근·비즈니스 로직 | 커밋(의존성이 담당) |
| **Repository** | `BaseRepository` 상속, 쿼리 캡슐화, N+1 회피(`get_all_with`) | 비즈니스 로직·커밋 |

> **주의:** `Service`는 세션을 주입받아 구성됩니다(`Service(session)`). 트랜잭션 커밋은 Service가 아니라 **기능 의존성**(`get_<name>_service`)이 요청 성공 시 수행합니다.

#### 마지막 단계 — `main.py` 의 `APPS` 에 등록

위 구조를 만든 뒤 `main.py` 의 `from app.domains import ...` 와 `APPS` 목록에 새 앱을 추가해야 라우터/Admin 이 연결됩니다. 모델은 앱 `__init__.py` 에서 import 하여 `Base.metadata` 에 등록합니다. (절차는 아래 [신규 모듈 개발 가이드](#신규-모듈-개발-가이드) 참고)

---

## 데이터 흐름

### 요청 처리 흐름

```
1. HTTP 요청 수신
       ↓
2. 미들웨어 처리 (CORS 검증 · User-Agent 파싱 · 접속 로그 수집)
       ↓
3. Router 진입 (파라미터 파싱 · Pydantic 검증 · Depends(get_<name>_service)로 Service 주입)
       ↓
4. Service 실행 (비즈니스 로직 · Repository 호출 · ORM 객체 반환)
       ↓
5. 응답 반환 (Pydantic 직렬화)
       ↓
6. 의존성 teardown — 성공 시 session.commit(), 예외 시 get_session 이 rollback()
```

### 코드 예시

```python
# dependencies — Service 구성 + 트랜잭션 경계
async def get_access_log_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[UserAccessLogService, None]:
    service = UserAccessLogService(session)
    yield service
    await session.commit()          # 요청 성공 시 커밋


# Router(view) — HTTP 역할만: 파라미터 → Service 호출 → 응답 변환
@router.get("/access-logs")
async def get_access_logs(
    skip: int = 0,
    limit: int = 50,
    service: UserAccessLogService = Depends(get_access_log_service),
):
    logs, total = await service.get_access_logs(skip, limit)
    return UserAccessLogListResponse(
        items=[UserAccessLogResponse.model_validate(log) for log in logs],
        total=total, skip=skip, limit=limit,
    )
```

### 트랜잭션 & 롤백

- **성공**: 뷰가 정상 반환 → `get_<name>_service` 가 `session.commit()`.
- **예외**: 뷰/Service 에서 예외 발생 → 커밋이 실행되지 않고 `get_session` teardown 이 `session.rollback()`.
- **요청 밖(Celery/백그라운드)**: `async with background_session() as session:` 컨텍스트로 커밋/롤백을 직접 관리(별도 풀).

---

## 핵심 패턴

### 1. Repository 패턴

데이터 접근 로직을 캡슐화하여 비즈니스 로직과 분리합니다.

```python
# app/core/repositories/repository_base.py (+ crud_base.py)
class BaseRepository(Generic[ModelType]):
    """제네릭 기본 Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # CRUD 기본 메서드
    async def create(self, data: dict) -> ModelType: ...
    async def get_by_id(self, id: str) -> ModelType | None: ...
    async def get_all(self, skip: int, limit: int) -> Sequence[ModelType]: ...
    async def update(self, id: str, data: dict) -> ModelType | None: ...
    async def delete(self, id: str) -> bool: ...

    # N+1 문제 해결 메서드
    async def get_by_id_with(self, id: str, relations: list[str]) -> ModelType | None: ...
    async def get_all_with(self, relations: list[str], strategy: str) -> Sequence[ModelType]: ...

    # 고급 쿼리
    async def get_or_create(self, filters: dict, defaults: dict) -> tuple[ModelType, bool]: ...
    async def update_or_create(self, filters: dict, data: dict) -> tuple[ModelType, bool]: ...
    async def bulk_create(self, items: list[dict]) -> list[ModelType]: ...
```

```python
# 모듈별 Repository 확장
class UserAccessLogRepository(BaseRepository[UserAccessLog]):
    """접속 로그 Repository"""

    model = UserAccessLog

    async def get_by_ip(self, ip_address: str) -> Sequence[UserAccessLog]:
        """IP 주소로 조회"""
        stmt = select(UserAccessLog).where(
            UserAccessLog.ip_address == ip_address
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_by_device_type(self) -> dict[str, int]:
        """장치 유형별 통계"""
        stmt = select(
            UserAccessLog.device_type,
            func.count().label("count")
        ).group_by(UserAccessLog.device_type)
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
```

### 2. 트랜잭션 경계 — 기능 의존성 (UnitOfWork 대체)

UnitOfWork 대신 **기능 의존성**이 세션으로 Service를 구성하고 요청 성공 시 커밋합니다.
트랜잭션 경계가 요청 수명주기와 일치해 예측 가능합니다.

```python
# app/domains/home/dependencies/access_log_dependencies.py
async def get_access_log_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[UserAccessLogService, None]:
    service = UserAccessLogService(session)
    yield service
    await session.commit()          # 요청 성공 시 커밋 (예외 시 get_session 이 롤백)
```

- 요청 밖(Celery/백그라운드)에서는 `async with background_session() as session:` 컨텍스트로
  커밋/롤백을 직접 관리합니다(별도 풀 → 메인 API 풀 고갈 방지).

### 3. Service 패턴

세션을 주입받아 Repository를 구성하고 비즈니스 로직을 캡슐화합니다(커밋은 의존성이 담당).

```python
# app/core/services/services_base.py - 공통 기반 클래스
class BaseService(LoggerMixin):
    """세션 주입 기반 Service. 커밋/롤백 경계는 의존성/컨텍스트가 책임진다."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session


# app/domains/home/services/user_access_log_service.py - 도메인 Service
class UserAccessLogService(BaseService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repository = UserAccessLogRepository(session)

    async def get_access_logs(
        self, skip: int = 0, limit: int = 50
    ) -> tuple[Sequence[UserAccessLog], int]:
        logs = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return logs, total
```

### 4. N+1 문제 해결

```python
# 문제: N+1 쿼리 발생
for user in users:
    print(user.posts)  # 각 사용자마다 추가 쿼리 발생

# 해결: Eager Loading
users = await repo.get_all_with(
    relations=["posts", "profile"],
    strategy="selectin"  # SELECT IN 전략
)

# Eager Loading 전략
# - selectin: SELECT ... WHERE id IN (...) - 대부분의 경우 권장
# - joined: LEFT OUTER JOIN - 1:1 관계에 적합
# - subquery: 서브쿼리 사용 - 복잡한 관계에 적합
```

---

## 시작하기

### 1. 저장소 클론

```bash
git clone https://github.com/your-repo/fastapi-default-project-structure.git
cd fastapi-default-project-structure
```

### 2. 가상환경 설정

```bash
# uv 사용 (권장)
uv sync
```

### 3. 환경 변수 설정

```bash
cp .env.sample .env
# .env 파일 수정
```

### 4. 데이터베이스 설정

```bash
# MySQL 데이터베이스 생성
mysql -u root -p
CREATE DATABASE fastapi_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. 서버 실행

```bash
# 개발 서버
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 6. 접속

- API 서버: http://localhost:8000
- API 문서: http://localhost:8000/docs
- 관리자 페이지: http://localhost:8000/admin
- 헬스체크: http://localhost:8000/health

---

## 환경 설정

### 주요 설정 항목

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `DEBUG` | `true` | 디버그 모드 (로그 레벨, 테이블 자동 생성, API 문서) |
| `ADMIN` | `true` | 관리자 페이지 활성화 (DEBUG와 독립적) |
| `ENV` | `development` | 환경 (development, staging, production) |
| `MYSQL_HOST` | `localhost` | MySQL 호스트 |
| `MYSQL_PORT` | `3306` | MySQL 포트 |
| `MYSQL_DATABASE` | `fastapi_db` | 데이터베이스 이름 |
| `REDIS_HOST` | `localhost` | Redis 호스트 |
| `LOG_FILE_ENABLED` | `true` | 파일 로그 활성화 |

### DEBUG 모드에 따른 동작

| 기능 | DEBUG=true | DEBUG=false |
|------|------------|-------------|
| 로그 레벨 | DEBUG | INFO |
| 테이블 자동 생성 | 활성화 | 비활성화 (Alembic 사용) |
| API 문서 (/docs) | 활성화 | 비활성화 |
| OpenAPI 스키마 | 활성화 | 비활성화 |
| Uvicorn reload | 활성화 | 비활성화 |

---

## 로깅 시스템

이 프로젝트는 Django 스타일의 구조화된 로깅 시스템을 제공합니다.

### 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                      Application Code                        │
│                   logger.info("message")                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                        get_logger()                          │
│          app/shared/logging/ (캐싱된 로거 반환)               │
└─────────────────────────────────────────────────────────────┘
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
┌─────────────────────────┐     ┌─────────────────────────┐
│    Console Handler       │     │     File Handlers        │
│  (stdout, 색상 지원)      │     │  (Rotating, 자동 분리)    │
└─────────────────────────┘     └─────────────────────────┘
              ↓                               ↓
         터미널 출력               ┌──────────┴──────────┐
                                  ↓                     ↓
                         logs/{date}_app.log    logs/{date}_error.log
                            (INFO+)                (ERROR+)
```

### 환경 변수 설정

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `LOG_CONSOLE_ENABLED` | `true` | 콘솔(터미널) 로그 출력 활성화 |
| `LOG_FILE_ENABLED` | `true` | 파일 로그 출력 활성화 |
| `LOG_LEVEL` | - | 전역 로그 레벨 (미설정 시 DEBUG 모드에 따라 자동 결정) |
| `LOG_CONSOLE_LEVEL` | - | 콘솔 로그 레벨 (미설정 시 자동 결정) |
| `LOG_FILE_LEVEL` | `INFO` | 파일 로그 레벨 |
| `LOG_DIR` | `logs` | 로그 파일 저장 디렉토리 |
| `LOG_APP_FILENAME` | `{date}_app.log` | 일반 로그 파일명 패턴 |
| `LOG_ERROR_FILENAME` | `{date}_error.log` | 에러 로그 파일명 패턴 |
| `LOG_MAX_SIZE_MB` | `10` | 단일 로그 파일 최대 크기 (MB) |
| `LOG_BACKUP_COUNT` | `5` | 보관할 백업 로그 파일 개수 |

### 자동 로그 레벨 결정

`LOG_LEVEL`을 설정하지 않으면 `DEBUG` 설정에 따라 자동 결정됩니다:

```
DEBUG=true  → 로그 레벨: DEBUG (모든 로그 출력)
DEBUG=false → 로그 레벨: INFO (INFO 이상만 출력)
```

### 사용 방법

#### 1. 기본 사용법

```python
from app.shared.logging import get_logger

# 모듈별 로거 생성 (이름으로 로그 출처 구분)
logger = get_logger("my_module")

# 로그 레벨별 출력
logger.debug("디버깅 정보")           # 개발 시 상세 정보
logger.info("일반 정보")              # 정상 동작 정보
logger.warning("경고 메시지")         # 잠재적 문제
logger.error("에러 발생")             # 오류 상황
logger.critical("심각한 오류")        # 시스템 중단 수준 오류
```

#### 2. 추가 정보와 함께 로깅

```python
# extra 파라미터로 추가 정보 포함
logger.error(
    "데이터베이스 연결 실패",
    extra={
        "host": "localhost",
        "port": 3306,
        "error_code": "CONNECTION_REFUSED"
    }
)

# 예외 정보 포함
try:
    result = some_operation()
except Exception as e:
    logger.exception("작업 실패", exc_info=True)  # 스택 트레이스 포함
```

#### 3. 서비스별 로거 활용

```python
# 각 서비스/모듈에서 고유 이름으로 로거 생성
# 이렇게 하면 로그에서 어떤 모듈에서 발생했는지 쉽게 구분 가능

# app/product/services/product_service.py
logger = get_logger("product_service")
logger.info(f"상품 생성 완료: {product.id}")

# app/user/services/user_service.py
logger = get_logger("user_service")
logger.info(f"사용자 로그인: {user.email}")

# 출력 예시:
# [2024-01-15 10:30:00] INFO     [product_service:create:45] 상품 생성 완료: abc123
# [2024-01-15 10:30:01] INFO     [user_service:login:78] 사용자 로그인: user@example.com
```

### 로그 파일 구조

```
logs/
├── 2024-01-15_app.log      # 일반 로그 (INFO 이상)
├── 2024-01-15_app.log.1    # 로테이션된 백업 파일
├── 2024-01-15_app.log.2
├── 2024-01-15_error.log    # 에러 로그 (ERROR 이상)
└── 2024-01-15_error.log.1
```

### 로그 포맷

기본 로그 포맷:
```
[{asctime}] {levelname:8} [{name}:{funcName}:{lineno}] {message}
```

출력 예시:
```
[2024-01-15 10:30:00] INFO     [main:startup:45] 애플리케이션 시작
[2024-01-15 10:30:01] DEBUG    [product_service:create:78] 상품 생성 시작: iPhone 15
[2024-01-15 10:30:02] ERROR    [database:connect:23] 연결 실패: timeout
```

### 미리 정의된 로거 상수

```python
# app/shared/logging/logger.py에 정의된 상수 (app.shared.logging에서 re-export)
from app.shared.logging import (
    HOME_LOGGER,      # "home"
    LYRIC_LOGGER,     # "lyric"
    SONG_LOGGER,      # "song"
    VIDEO_LOGGER,     # "video"
    CELERY_LOGGER,    # "celery"
    APP_LOGGER,       # "app"
)

logger = get_logger(HOME_LOGGER)
```

---

## 접속 로그 미들웨어

모든 API 요청의 접속 정보를 자동으로 수집하고 데이터베이스에 저장하는 미들웨어입니다.

### 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                        HTTP Request                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   UserInfoMiddleware                         │
│  1. 요청 시작 시간 기록                                        │
│  2. User-Agent 파싱 (OS, 브라우저, 디바이스)                    │
│  3. IP 주소 추출 (프록시 환경 지원)                             │
│  4. 요청 정보 수집                                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      API 처리 (Router)                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   UserInfoMiddleware                         │
│  5. 응답 시간 계산                                             │
│  6. asyncio.create_task로 DB 저장 (Non-blocking)              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                       HTTP Response                          │
└─────────────────────────────────────────────────────────────┘
```

### 환경 변수 설정

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `ACCESS_LOG_ENABLED` | `true` | 접속 로그 수집 활성화 |
| `ACCESS_LOG_EXCLUDE_PATHS` | `["/health", ...]` | 로그 수집 제외 경로 (JSON 배열) |
| `ACCESS_LOG_EXCLUDE_EXTENSIONS` | `[".css", ...]` | 로그 수집 제외 확장자 (JSON 배열) |

### 기본 제외 경로 및 확장자

```python
# 기본 제외 경로
ACCESS_LOG_EXCLUDE_PATHS = [
    "/health",           # 헬스체크
    "/docs",             # API 문서
    "/redoc",            # ReDoc
    "/openapi.json",     # OpenAPI 스키마
    "/favicon.ico",      # 파비콘
]

# 기본 제외 확장자
ACCESS_LOG_EXCLUDE_EXTENSIONS = [
    ".css", ".js", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg"
]
```

### 커스텀 제외 설정

`.env` 파일에서 JSON 배열 형식으로 설정:

```bash
# 제외 경로 추가
ACCESS_LOG_EXCLUDE_PATHS=["/health", "/docs", "/admin", "/metrics", "/internal"]

# 제외 확장자 추가
ACCESS_LOG_EXCLUDE_EXTENSIONS=[".css", ".js", ".ico", ".png", ".woff2", ".map"]
```

### 수집 정보

#### 네트워크 정보

| 필드 | 설명 |
|------|------|
| `ip_address` | 클라이언트 IP 주소 |
| `forwarded_for` | X-Forwarded-For 헤더 (프록시 경유 시) |
| `real_ip` | X-Real-IP 헤더 (Nginx 등) |

#### User-Agent 파싱 정보

| 필드 | 설명 | 예시 |
|------|------|------|
| `user_agent` | 원본 User-Agent 문자열 | `Mozilla/5.0 (Windows NT 10.0...)` |
| `os_name` | 운영체제 이름 | `Windows`, `iOS`, `Android` |
| `os_version` | 운영체제 버전 | `10.0`, `17.2`, `14` |
| `browser_name` | 브라우저 이름 | `Chrome`, `Safari`, `Firefox` |
| `browser_version` | 브라우저 버전 | `120.0.0`, `17.2` |
| `device_type` | 장치 유형 | `desktop`, `mobile`, `tablet` |
| `device_brand` | 장치 제조사 | `Apple`, `Samsung` |
| `device_model` | 장치 모델 | `iPhone`, `Galaxy S24` |
| `is_bot` | 봇 여부 | `true`, `false` |

#### 요청/응답 정보

| 필드 | 설명 |
|------|------|
| `request_path` | 요청 경로 (`/api/v1/home/access-logs`) |
| `request_method` | HTTP 메서드 (`GET`, `POST`, ...) |
| `query_string` | 쿼리 스트링 (`?page=1&limit=10`) |
| `referer` | Referer 헤더 |
| `response_status` | HTTP 응답 상태 코드 |
| `response_time_ms` | 응답 시간 (밀리초) |

#### 사용자 정보

| 필드 | 설명 |
|------|------|
| `session_id` | 세션 ID (쿠키에서 추출) |
| `user_id` | 인증된 사용자 ID |
| `accept_language` | Accept-Language 헤더 |

### 데이터베이스 모델

`user_access_logs` 테이블에 저장되며, 다음 인덱스가 설정되어 있습니다:

```python
# 인덱스 설정 (검색 최적화)
- ip_address        # IP별 조회
- created_at        # 시간별 조회
- device_type       # 장치 유형별 통계
- os_name          # OS별 통계
- browser_name     # 브라우저별 통계
- session_id       # 세션별 조회
- user_id          # 사용자별 조회
```

### API 엔드포인트

접속 로그 조회 API가 제공됩니다:

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/home/access-logs` | 접속 로그 목록 (페이지네이션) |
| GET | `/api/v1/home/access-logs/recent` | 최근 접속 로그 |
| GET | `/api/v1/home/access-logs/by-ip/{ip}` | IP별 접속 로그 |
| GET | `/api/v1/home/access-logs/by-user/{user_id}` | 사용자별 접속 로그 |
| GET | `/api/v1/home/access-logs/stats` | 접속 통계 (장치, OS, 브라우저별) |

### 활용 예시

#### 통계 대시보드 구현

```python
# 접속 통계 조회
stats = await service.get_stats()

# 응답 예시
{
    "total_count": 15420,
    "device_types": [
        {"device_type": "desktop", "count": 8500},
        {"device_type": "mobile", "count": 6200},
        {"device_type": "tablet", "count": 720}
    ],
    "os_list": [
        {"os_name": "Windows", "count": 6000},
        {"os_name": "iOS", "count": 4500},
        {"os_name": "Android", "count": 3200}
    ],
    "browsers": [
        {"browser_name": "Chrome", "count": 9000},
        {"browser_name": "Safari", "count": 4000}
    ]
}
```

#### IP 기반 접속 추적

```python
# 특정 IP의 접속 기록 조회
logs = await service.get_logs_by_ip("192.168.1.100")

# 의심스러운 활동 감지
suspicious = [log for log in logs if log.is_bot and log.response_status == 403]
```

### 성능 고려사항

1. **Non-blocking 저장**: 접속 로그는 `asyncio.create_task()`로 백그라운드에서 저장되어 API 응답 시간에 영향을 주지 않습니다.

2. **분리된 커넥션 풀**: 접속 로그 sink는 `background_session()`(별도 백그라운드 풀)을 사용하여 메인 API 풀 고갈을 방지합니다.

3. **제외 설정 최적화**: 헬스체크, 정적 파일 등 빈번한 요청은 기본적으로 제외됩니다.

4. **인덱스 활용**: 자주 조회되는 필드에 인덱스가 설정되어 있습니다.

```python
# 미들웨어 내부 동작
async def dispatch(self, request: Request, call_next: Callable):
    # 제외 경로 체크 (빠른 반환)
    if self._should_skip(request.url.path):
        return await call_next(request)

    # 요청 처리
    response = await call_next(request)

    # 백그라운드에서 비동기 저장 (응답 지연 없음)
    # 태스크 참조를 유지하여 GC에 의한 소실 방지
    task = asyncio.create_task(self._save_access_log(data))
    self._background_tasks.add(task)
    task.add_done_callback(self._background_tasks.discard)
    return response
```

---

## 신규 모듈 개발 가이드

> 상세 아키텍처 및 각 파일의 역할은 **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** 를 참고하세요.

새 앱은 스캐폴딩으로 디렉토리/파일을 생성한 뒤 **`main.py` 의 `APPS` 목록에 등록**합니다.
등록을 빠뜨리면 라우터/Admin 이 연결되지 않습니다.

### 스캐폴딩 생성기 사용 (권장)

```bash
# 기본 구조 생성 (router + dependencies)
uv run python -m scripts.new_app <name>

# Celery 워커 + SQLAdmin 포함
uv run python -m scripts.new_app <name> --with-admin
```

### 최소 절차 (3단계)

**1. 스캐폴딩 생성 + 도메인 코드 작성** (`models/`, `schemas/`, `repositories/`, `services/`, `api/routers/`)

**2. `main.py` 의 `APPS` 에 등록**

```python
# main.py
from app.domains import blog, home, reply, sns, user, <name>   # ← import 추가

APPS = [home, blog, reply, sns, user, <name>]   # ← 목록에 추가 (순서 = 로드 순서)
```

각 앱 패키지의 `__init__.py` 가 `router`(및 선택 `admin_views`)를 공개하므로, `main.py` 는 `APPS` 를 순회하며 `include_router(prefix="/api")` 로 취합합니다. 모델은 앱 `__init__.py` 의 models import(주석 해제)로 `Base.metadata` 에 등록됩니다.

**3. 서버 재시작** — `APPS` 에 추가한 앱의 라우터가 마운트됩니다.

### 개발 체크리스트

- [ ] `main.py` 의 `APPS` 에 앱 등록 (라우터/Admin 취합) + `__init__.py` models import(메타데이터)
- [ ] `models/` — SQLAlchemy ORM 모델
- [ ] `repositories/` — BaseRepository 확장
- [ ] `dependencies/` — 기능 의존성(Service 구성 + 트랜잭션 경계)
- [ ] `services/` — 비즈니스 로직
- [ ] `schemas/` — Pydantic 요청/응답 스키마
- [ ] `api/routers/router.py` + `v1/` — 엔드포인트 정의
- [ ] `tests/` — pytest 테스트
- [ ] Celery 태스크는 중앙 `app/celery/tasks.py` 에 추가 (선택)
- [ ] `admin.py` (선택 — `--with-admin`)

---

## API 문서

### 접근 URL

| 문서 | URL | 조건 |
|------|-----|------|
| Scalar API 문서 | http://localhost:8000/docs | DEBUG=true |
| OpenAPI JSON | http://localhost:8000/openapi.json | DEBUG=true |
| 관리자 페이지 | http://localhost:8000/admin | ADMIN=true |
| 헬스체크 | http://localhost:8000/health | 항상 |

### 현재 구현된 API

#### Home 모듈 (접속 로그)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/home/access-logs` | 접속 로그 목록 (페이지네이션) |
| GET | `/api/v1/home/access-logs/recent` | 최근 접속 로그 |
| GET | `/api/v1/home/access-logs/by-ip/{ip}` | IP별 접속 로그 |
| GET | `/api/v1/home/access-logs/by-user/{user_id}` | 사용자별 접속 로그 |
| GET | `/api/v1/home/access-logs/stats` | 접속 통계 |

---

## 참고 자료

- [FastAPI 공식 문서](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 문서](https://docs.sqlalchemy.org/en/20/)
- [Pydantic v2 문서](https://docs.pydantic.dev/latest/)
- [How to structure your FastAPI projects](https://medium.com/@amirm.lavasani/how-to-structure-your-fastapi-projects-0219a6600a8f)

---

## 라이선스

MIT License
