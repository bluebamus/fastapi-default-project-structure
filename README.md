# FastAPI Default Project Structure

Repository 패턴과 계층 분리 아키텍처를 적용한 FastAPI 프로젝트 템플릿입니다.
표준 FastAPI 배선을 따릅니다: 각 기능 패키지(`app/features/<name>/__init__.py`)가 하위 뷰 라우터를 취합한 `router` 를 공개하고, `main.py` 가 이를 명시적 `include_router` 호출로 최종 취합하며 앱 설정을 구성합니다.

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
- [인증 (JWT)](#인증-jwt)
- [레이트 리밋](#레이트-리밋)
- [신규 기능 개발 가이드](#신규-기능-개발-가이드)
- [API 문서](#api-문서)

---

## 개요

이 프로젝트는 FastAPI 기반의 확장 가능한 백엔드 애플리케이션 템플릿입니다.

### 주요 특징

- **계층 분리 아키텍처**: Router → Service → Repository → Database
- **명시적 트랜잭션 경계**: 기능 의존성(`get_<name>_service`)은 Service 구성만 담당하고, 커밋은 **쓰기 핸들러 본문**이 `await service.commit()` 로 수행(UnitOfWork 미사용)
- **읽기/쓰기 세션 분리**: 조회 전용 의존성(`get_<name>_service_readonly`)은 `get_read_session` 을 받아 커밋하지 않음 — 예외 시 세션 teardown이 롤백
- **인증(JWT)**: OAuth2 Password 플로우 + JWT access/refresh 토큰, bcrypt 비밀번호 해시 (`auth` 기능, `app/utils/authenticator/`)
- **레이트 리밋**: slowapi 데코레이터 기반 라우트별 한도(`app/core/rate_limit.py`, `RATE_LIMIT_ENABLED` 로 토글)
- **N+1 문제 해결**: Eager Loading 전략 내장 (selectin, joined, subquery)
- **유연한 설정**: Pydantic Settings 기반 환경 변수 관리
- **구조화된 로깅**: 콘솔/파일 로그 분리, 자동 로그 로테이션
- **API 문서**: Scalar UI 기반 인터랙티브 문서
- **관리자 페이지**: SQLAdmin 통합

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| Framework | FastAPI 0.141+ |
| ORM | SQLAlchemy 2.0 (async) |
| Database | MySQL (aiomysql) |
| Validation | Pydantic v2 |
| Migration | Alembic |
| Message Broker | Redis (Celery 브로커·결과 백엔드 전용 — 앱 캐시로는 쓰지 않음) |
| Admin | SQLAdmin |
| API Docs | Scalar |
| Task Queue | Celery + Redis |
| Auth | OAuth2 Password + JWT(PyJWT) + bcrypt |
| Rate Limit | slowapi |

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

트랜잭션 경계는 **쓰기 핸들러 본문**이 담당합니다. `get_<name>_service` 가 세션으로 Service를
구성해 뷰에 주입하면, 핸들러가 작업을 마친 뒤 응답을 만들기 전에 `await service.commit()` 을
호출합니다(예외 시 `get_session` teardown 이 롤백). 조회 엔드포인트는
`get_<name>_service_readonly` 를 써서 `get_read_session` 을 받고 커밋하지 않습니다.
요청 밖(백그라운드/Celery)에서는 `background_session()` 컨텍스트(별도 풀)를 사용해
메인 API 풀 고갈을 방지합니다.

---

## 프로젝트 구조

> 상세한 아키텍처 설명은 **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** 를 참고하세요.

```
fastapi-default-project-structure/
├── main.py                      # 진입점: 각 기능의 router 를 include_router 로 취합 + 앱 설정
├── config.py                    # 환경 설정 (Pydantic Settings) — 설정 단일 출처
├── pyproject.toml               # 의존성 및 도구 설정 ([tool.uv] package = false)
├── alembic.ini                  # Alembic 설정
├── .env.example                 # 설정 예시 (config.py 와 양방향 일치를 테스트가 강제)
├── .pre-commit-config.yaml      # ruff + 기본 위생 훅
│
├── app/
│   ├── features/                # 기능 단위 vertical slice — main.py 가 include_router 로 취합
│   │   ├── admin.py             # SQLAdmin 취합 — ADMIN_VIEWS + 조립 함수 3종
│   │   └── <name>/              # 각 기능 디렉토리
│   │       ├── __init__.py      # router 공개 + models import (admin 은 재노출하지 않음)
│   │       ├── admin.py         # 이 기능 모델의 ModelView + admin_views (선택)
│   │       ├── api/routers/     # router.py + v1/ 엔드포인트
│   │       ├── models/          # SQLAlchemy ORM 모델
│   │       ├── schemas/         # Pydantic 스키마
│   │       ├── services/        # 비즈니스 로직
│   │       ├── repositories/    # 데이터 접근 계층
│   │       ├── dependencies/    # 기능 의존성 (Service 구성 — 커밋은 핸들러)
│   │       ├── exceptions.py    # 기능 예외 (선택)
│   │       └── tests/           # 이 기능의 테스트
│   ├── core/                    # 프레임워크 인프라 (features 가 의존)
│   │   ├── exception.py         # 공통 예외 계층
│   │   ├── rate_limit.py        # slowapi limiter + 초과 핸들러
│   │   ├── tags_metadata.py     # OpenAPI 태그 설명
│   │   ├── db/                  # 세션·라우팅·모델 등록
│   │   │   ├── session.py       # 엔진, get_session / get_read_session, background_session
│   │   │   ├── router.py        # 읽기/쓰기 라우팅 (RoutingSession)
│   │   │   └── models_registry.py  # 모델 import 단일 지점 (SSOT)
│   │   ├── models/models_base.py   # SQLAlchemy Base + TimestampMixin·UUIDMixin
│   │   ├── repositories/        # BaseRepository (제네릭 CRUD)
│   │   ├── services/            # BaseService
│   │   └── middlewares/         # CORS, UserInfo, AccessLogSink, background_tasks
│   │
│   ├── celery/                  # 중앙 Celery 앱 + tasks.py + run_async 브릿지
│   └── utils/                   # logs(구조화 로깅) · authenticator(JWT·bcrypt) ·
│                                #   pagination · validators
│
├── tests/                       # 횡단 테스트 — core 계약·배선·교차 기능
│   ├── core/                    # 설정 계약, admin 뷰 정책, 마이그레이션 체인 등
│   ├── utils/                   # 로깅·인증·페이지네이션 유틸
│   └── test_*.py                # 라우터/admin 배선, 응답 직렬화, 레이트리밋 등
│
├── migrations/                  # Alembic (env.py 가 import_all_models() SSOT 로 메타데이터 수집)
├── .github/workflows/ci.yml     # CI 게이트 (ruff · format · mypy 콜드캐시 · pytest · bandit · alembic)
├── docs/
│   ├── ARCHITECTURE.md          # 아키텍처 공식 문서 (SSOT)
│   └── QUICKSTART.md            # 최소 실행 경로
└── logs/ media/ static/ poc/    # 런타임·예약 디렉터리 (.gitkeep 만 추적)
```

> 기능 테스트는 `app/features/<name>/tests/` 에, 여러 기능에 걸치거나 `core` 계약을 보는 테스트는
> 최상위 `tests/` 에 둡니다. `pytest` 는 양쪽을 모두 수집합니다.

### 핵심 파일 설명

| 파일 | 설명 |
|------|------|
| `main.py` | FastAPI 조립 — 각 기능 `router` 를 명시 `include_router(prefix="/api")` 로 취합 + 미들웨어/예외/문서/lifespan/Admin 설정 |
| `app/features/<name>/__init__.py` | 하위 뷰 라우터를 취합한 `router` 공개 — `main.py` 가 명시 import 후 `include_router` 로 취합 |
| `app/features/<name>/admin.py` | 기능이 소유한 SQLAdmin ModelView + `admin_views` |
| `app/features/admin.py` | 기능별 `admin_views` 를 명시 import 로 취합(`ADMIN_VIEWS`). `main.py` 는 `register_admin(app, engine)` 하나만 호출하고, 내부에서 `create_admin_interface()`(생성·마운트) → `register_admin_views()`(등록) 순으로 위임 |
| `app/core/db/session.py` | SQLAlchemy 엔진, 세션 팩토리, 커넥션 풀, `background_session` |
| `app/features/<name>/dependencies/` | 기능 의존성 — Service 구성(쓰기용 `get_session` / 조회용 `get_read_session`). 커밋은 핸들러가 수행 |
| `app/core/exception.py` | 커스텀 예외 계층 (4xx, 5xx, 비즈니스 예외) |
| `migrations/env.py` | `import_all_models()`(SSOT) 로 전 기능 모델을 자동 수집 → Alembic autogenerate |

### `app/` 구현 규칙 (Conventions)

`app/` 아래는 **3개 영역**으로 나뉘며, 의존은 한 방향으로만 흐릅니다.

```
features → core → utils
```

| 영역 | 역할 | 규칙 |
|------|------|------|
| `app/features/<name>/` | 기능 단위 vertical slice | 비즈니스 코드는 전부 여기. `core`를 사용하고 다른 기능은 import하지 않음(예외: `auth` 는 횡단 관심사로 `user` 의 식별 모델·리포지토리에 의존 — `auth_service` 에 명시) |
| `app/core/` | 프레임워크 인프라 (Base*, db, 미들웨어) | 원칙적으로 기능 구현을 직접 알지 않는다. 유일한 예외는 `db/session.py` 의 `create_db_tables()`가 메타데이터 등록을 위해 `import_all_models()`를 함수 내부에서 호출하는 것 |
| `app/utils/` | 순수 유틸리티 (로깅, 인증, 페이지네이션) | 외부·상위 계층 의존 없음. 누구나 import 가능 |

> 핵심 규칙: **`core`는 기능 구현을 직접 결합하지 않는다.** 기능이 `core`의 미들웨어 등에 자신을 연결해야 할 때는 직접 import가 아니라 등록 훅(예: `access_log_sink.register_sink()`)을 통한다.

#### 기능 표준 레이아웃

새 앱은 아래 구조와 **파일 네이밍 표준**을 따릅니다. (기준 구현체: `app/features/home/`)

```
app/features/<name>/
├── api/
│   └── routers/
│       ├── router.py          # 앱 루트 라우터 (v1/ 등을 묶음) — 필수
│       └── v1/<name>.py       # 버전별 엔드포인트 — 필수
├── models/models.py           # SQLAlchemy ORM 모델 — 필수
├── schemas/                   # Pydantic 요청/응답 스키마 — 필수
├── repositories/              # BaseRepository 확장 (데이터 접근) — 필수
├── services/                  # BaseService 확장 (비즈니스 로직) — 필수
├── dependencies/              # 기능 의존성 (Service 구성 — 커밋은 핸들러) — 필수
│   └── <name>_dependencies.py
├── tests/                     # pytest — 필수
├── exceptions.py              # 기능 예외 — 선택
└── admin.py                   # SQLAdmin ModelView — 선택

# Celery 태스크는 기능별 worker/가 아니라 중앙 app/celery/tasks.py 에 정의한다.
```

**파일 네이밍 표준 (반드시 준수):**

| 용도 | 올바른 이름 | 쓰지 말 것 |
|------|------------|-----------|
| 기능 예외 | `exceptions.py` | `<name>_exception.py` |
| FastAPI 의존성 | `dependencies.py` | `dependency.py` |
| SQLAdmin 뷰 | `admin.py` | `api/<name>_admin.py` |
| Celery 태스크 | 중앙 `app/celery/tasks.py` | 기능별 `worker/` |
| 기능 의존성 | `dependencies/` 패키지 | 단일 `dependencies.py`도 허용 |

#### 계층별 책임과 호출 규칙

```
Router  →  Depends(get_<name>_service)  →  Service(session)  →  Repository  →  DB
 (API·                (Service 구성)          (비즈니스 로직)     (데이터 접근)
 트랜잭션 경계)
```

| 계층 | 하는 일 | 하지 말 것 |
|------|---------|-----------|
| **Router** | 입력 검증(Pydantic), `Depends(get_<name>_service)`로 Service 주입, Service 호출 → **쓰기면 `await service.commit()`** → 응답 변환 | 직접 ORM 쿼리 |
| **Dependency** | 세션 주입(쓰기 `get_session` / 조회 `get_read_session`) → `Service(session)` 구성 후 **반환**(`yield` 아님) | 비즈니스 로직·커밋 |
| **Service** | `BaseService` 상속, `self.session`/Repository로 데이터 접근·비즈니스 로직 | 커밋 시점 결정(핸들러가 담당) |
| **Repository** | `BaseRepository` 상속, 쿼리 캡슐화, N+1 회피(`get_all_with`) | 비즈니스 로직·커밋 |

> **주의:** `Service`는 세션을 주입받아 구성됩니다(`Service(session)`). 트랜잭션 커밋은 Service 도 의존성도 아닌 **쓰기 핸들러 본문**이 응답 반환 직전에 수행합니다.
>
> 의존성이 `yield` 후에 커밋하던 이전 방식은 FastAPI 상위 버전에서 yield dependency 의 종료 코드가 **응답 전송 후에** 실행되도록 바뀌면서, 커밋이 실패해도 클라이언트가 `201` 을 받는 문제가 있었습니다. 커밋을 핸들러 안으로 옮겨 응답 생성 전에 끝나도록 보장합니다.

#### 마지막 단계 — `main.py` 에 라우터 명시 등록

위 구조를 만든 뒤 `main.py` 의 `from app.features import ...` 에 이름을 추가하고 `app.include_router(<name>.router, prefix="/api")` 한 줄을 넣어야 라우터가 연결됩니다. 모델은 기능 `__init__.py` 에서 import 하며, `models_registry` 가 `app/features/<name>/models/models.py` 를 자동 수집합니다. Admin 은 `app/features/<name>/admin.py` 에 ModelView 와 `admin_views` 를 만들고, `app/features/admin.py` 의 import 와 `ADMIN_VIEWS` 에 한 줄씩 더합니다. (절차는 아래 [신규 기능 개발 가이드](#신규-기능-개발-가이드) 참고)

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
5. 쓰기 핸들러면 await service.commit() — 여기서 트랜잭션이 닫힌다
       ↓
6. 응답 반환 (Pydantic 직렬화)
       ↓
7. 의존성 teardown — 예외로 빠져나갔다면 get_session 이 rollback()
```

### 코드 예시

```python
# dependencies — Service 구성만 담당(커밋하지 않는다)
async def get_blog_service(
    session: AsyncSession = Depends(get_session),          # 쓰기용
) -> BlogService:
    return BlogService(session)


async def get_blog_service_readonly(
    session: AsyncSession = Depends(get_read_session),     # 조회용 — 커밋 없음
) -> BlogService:
    return BlogService(session)


# Router(view) — 쓰기: 파라미터 → Service 호출 → commit → 응답 변환
@router.post("/posts", response_model=PostResponse, status_code=201)
async def create_post(
    payload: PostCreate,
    service: BlogService = Depends(get_blog_service),
) -> PostResponse:
    post = await service.create_post(payload)
    await service.commit()          # 응답 생성 전에 커밋을 끝낸다
    return PostResponse.model_validate(post)


# Router(view) — 조회: 읽기 전용 의존성을 쓰고 커밋하지 않는다
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

- **성공**: 쓰기 핸들러가 응답 생성 전에 `await service.commit()` 을 호출한다.
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
# 기능별 Repository 확장
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

### 2. 트랜잭션 경계 — 쓰기 핸들러 (UnitOfWork 대체)

UnitOfWork 대신 **쓰기 핸들러**가 커밋 시점을 쥡니다. 기능 의존성은 세션으로 Service를
구성해 넘겨주기만 하고, 커밋은 하지 않습니다. 커밋이 응답 생성보다 먼저 끝나므로
커밋 실패가 성공 응답으로 둔갑하지 않습니다.

```python
# app/features/blog/dependencies/blog_dependencies.py — 구성만 한다
async def get_blog_service(
    session: AsyncSession = Depends(get_session),          # 쓰기용
) -> BlogService:
    return BlogService(session)


async def get_blog_service_readonly(
    session: AsyncSession = Depends(get_read_session),     # 조회용
) -> BlogService:
    return BlogService(session)


# app/features/blog/api/routers/v1/blog.py — 커밋은 여기서
async def create_post(
    payload: PostCreate,
    service: BlogService = Depends(get_blog_service),
) -> PostResponse:
    post = await service.create_post(payload)
    await service.commit()          # 예외 시 get_session teardown 이 롤백
    return PostResponse.model_validate(post)
```

- 조회 엔드포인트는 `_readonly` 의존성을 써서 `get_read_session` 을 받습니다. 불필요한
  COMMIT 왕복이 사라지고, `DB_ROUTER_ENABLED` 가 켜지면 replica 로 라우팅됩니다.
  읽기 핸들러가 몰래 쓰기를 시도하면 `ReadOnlyRoutingError` 로 즉시 실패합니다.
- 요청 밖(Celery/백그라운드)에서는 `async with background_session() as session:` 컨텍스트로
  커밋/롤백을 직접 관리합니다(별도 풀 → 메인 API 풀 고갈 방지).

### 3. Service 패턴

세션을 주입받아 Repository를 구성하고 비즈니스 로직을 캡슐화합니다(커밋 시점은 핸들러가 결정).

```python
# app/core/services/services_base.py - 공통 기반 클래스
class BaseService(LoggerMixin):
    """세션 주입 기반 Service. 커밋/롤백 경계는 핸들러/컨텍스트가 책임진다."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session


# app/features/home/services/user_access_log_service.py - 기능 Service
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

> **처음이라면 [docs/QUICKSTART.md](docs/QUICKSTART.md) 부터.** 인프라 없이 30초 만에
> 기동을 확인하는 최소 경로와, 첫 실행에서 가장 자주 막히는 지점(`DEBUG=true` 기본값이
> MySQL을 요구한다)을 다룬다. 아래는 전체 설치 절차다.

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
cp .env.example .env
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
| `ADMIN` | `true` | 관리자 페이지 활성화 (DEBUG와 독립적). **인증 없음** — 운영은 `false` 명시 |
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

이 프로젝트는 구조화된 로깅 시스템을 제공합니다.

### 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                      Application Code                        │
│                   logger.info("message")                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                        get_logger()                          │
│          app/utils/logs/ (캐싱된 로거 반환)                   │
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
from app.utils.logs import get_logger

# 기능별 로거 생성 (이름으로 로그 출처 구분)
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
# 각 서비스/기능에서 고유 이름으로 로거 생성
# 이렇게 하면 로그에서 어떤 기능에서 발생했는지 쉽게 구분 가능

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

### 로거 이름 규칙

별도의 상수 없이 기능/출처를 나타내는 문자열로 로거를 만든다(예: `"home"`, `"database"`,
`"celery"`). 로그 헤더의 `[app=..]` 세그먼트가 소스 경로에서 앱을 자동 식별한다.

```python
from app.utils.logs import get_logger

logger = get_logger("home")  # 이름은 로그에서 출처를 구분하는 문자열
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
| GET | `/api/v1/home/access-logs/by-ip/{ip_address}` | IP별 접속 로그 |
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

## 인증 (JWT)

OAuth2 **password flow** + JWT access/refresh 토큰. 비밀번호는 bcrypt 해시로 저장합니다.
자격증명은 `user` 기능의 `User.hashed_password` 에 두고, `auth` 는 인증 로직만 담당합니다
(횡단 관심사라 `auth → user` 의존은 의도된 예외입니다).

- 기능: `app/features/auth/`
- 토큰 유틸: `app/utils/authenticator/`

### 엔드포인트

| 메서드 | 경로 | 인증 | 요청 | 성공 | 실패 |
|---|---|---|---|---|---|
| `POST` | `/api/v1/auth/register` | — | JSON | `201` | `409` 사용자명 중복 · `422` 검증 |
| `POST` | `/api/v1/auth/login` | — | **form** | `200` | `401` 자격증명 불일치 · `422` |
| `POST` | `/api/v1/auth/refresh` | — | JSON | `200` | `401` 토큰 무효·만료 · `422` |
| `GET` | `/api/v1/auth/me` | Bearer | — | `200` | `401` |

> `login` 만 `application/x-www-form-urlencoded` 입니다 — OAuth2 password flow 규격이라
> `username`·`password` 를 form 필드로 받습니다. 나머지는 JSON 입니다.

### 사용 예시

```bash
# 1) 가입 — 비밀번호는 8자 이상
curl -X POST localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"secret-pw-1234"}'

# 2) 로그인 — form 전송(-d 기본값이 form 이므로 헤더 불요)
curl -X POST localhost:8000/api/v1/auth/login \
  -d 'username=alice&password=secret-pw-1234'
# → {"access_token":"eyJ...","refresh_token":"eyJ...","token_type":"bearer"}

# 3) 보호 엔드포인트 호출
curl localhost:8000/api/v1/auth/me -H 'Authorization: Bearer <access_token>'

# 4) 재발급 — access 가 만료되면 refresh 로 둘 다 새로 받는다
curl -X POST localhost:8000/api/v1/auth/refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<refresh_token>"}'
```

### 토큰 정책

| 설정 | 기본값 | 설명 |
|---|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access Token 수명(분) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh Token 수명(일) |
| `JWT_ALGORITHM` | `HS256` | 서명 알고리즘 |
| `ACCESS_TOKEN_SECRET_KEY` | `change-this-...` | Access 서명 키 |
| `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` | Refresh 서명 키 (access 와 **다른 값** 권장) |

- `refresh` 는 access·refresh 를 **둘 다** 새로 발급합니다(refresh 토큰 회전).
- 토큰에는 종류 표식이 들어 있어 access 토큰을 refresh 자리에 넣으면 거부됩니다.
- 비활성 사용자(`is_active=false`)는 재발급 단계에서 차단됩니다.

> **운영 배포 전 필수:** 두 서명 키는 `.env` 에서 반드시 교체하세요. 기본값
> (`change-this-...`)이 그대로면 누구나 토큰을 위조할 수 있습니다. 서버 측 토큰 폐기
> 목록(블랙리스트)은 구현돼 있지 않으므로, 유출된 refresh 토큰은 만료까지 유효합니다 —
> 짧은 수명이 필요하면 `REFRESH_TOKEN_EXPIRE_DAYS` 를 줄이세요.

### 보안 설계 메모

- **상수 시간 인증** — 사용자가 없어도 더미 해시로 bcrypt 검증을 상시 수행합니다. 응답
  시간차로 사용자명 존재 여부를 알아내는 열거 공격을 막습니다.
- **논블로킹 해싱** — bcrypt 는 `asyncio.to_thread` 로 격리합니다. 동기 호출하면 로그인마다
  이벤트 루프가 수백 ms 멈춥니다.
- **관리 화면 노출 차단** — `hashed_password` 는 SQLAdmin 의 목록·상세·폼·내보내기 어디에도
  나오지 않으며, `User` 는 admin 생성이 막혀 있습니다(비밀번호 없이 만들면 로그인 불가
  계정이 쌓입니다). 구조 증거: `tests/core/test_admin_views.py`.

---

## 레이트 리밋

slowapi **데코레이터 기반**입니다. 전역 미들웨어(`SlowAPIMiddleware`)는 쓰지 않습니다 —
라우트마다 한도를 달리 줄 수 있고, 어떤 엔드포인트가 보호되는지 코드에서 바로 보입니다.

- 구현: `app/core/rate_limit.py`
- 클라이언트 식별: `get_remote_address` (요청 IP)

### 설정

| 설정 | 기본값 | 설명 |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | 끄면 데코레이터가 무동작 |
| `RATE_LIMIT_DEFAULT` | `100/minute` | 데코레이터 기본 한도 (slowapi 형식 `<count>/<period>`) |

### 현재 적용 대상

| 엔드포인트 | 한도 |
|---|---|
| `POST /api/v1/auth/register` | `RATE_LIMIT_DEFAULT` |
| `POST /api/v1/auth/login` | `RATE_LIMIT_DEFAULT` |

인증 진입점 두 곳에만 걸려 있습니다. 무차별 대입과 대량 가입이 실제 위험 지점이기 때문입니다.
초과 시 `429 Too Many Requests` 를 반환합니다.

### 새 라우트에 적용하기

```python
from fastapi import Request
from app.core.rate_limit import limiter
from config import middleware_settings


@router.post("/items")
@limiter.limit(middleware_settings.RATE_LIMIT_DEFAULT)   # 또는 "5/minute" 처럼 직접 지정
async def create_item(request: Request, ...):            # request 파라미터 필수
    ...
```

> **`request: Request` 파라미터가 반드시 있어야 합니다.** slowapi 가 이 인자에서 클라이언트
> IP 를 꺼내므로, 빠뜨리면 기동 시점에 에러가 납니다.

> **한계 — 카운터가 프로세스 메모리에 있습니다.** 워커를 여러 개 띄우면 각 워커가 자기
> 카운터를 세므로 실질 한도가 워커 수만큼 늘어납니다. 정확한 전역 한도가 필요하면 slowapi 를
> Redis 스토리지로 전환하거나 리버스 프록시 단에서 거세요. 테스트에서는
> `RATE_LIMIT_ENABLED=false` 로 꺼 둡니다(in-memory 카운터가 테스트 간에 공유되면
> 순서에 따라 실패합니다).

---

## 신규 기능 개발 가이드

> 상세 아키텍처 및 각 파일의 역할은 **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** 를 참고하세요.

새 기능은 `app/features/<name>/` vertical slice 를 만든 뒤 **`main.py` 에 라우터를 명시 등록**합니다.
등록을 빠뜨리면 라우터가 연결되지 않습니다.

### 최소 절차 (3단계)

**1. `app/features/<name>/` 생성 + 코드 작성** (`api/routers/`, `models/`, `schemas/`, `repositories/`, `services/`, `dependencies/`)
`__init__.py` 는 `router` 를 공개하고 `models` 모듈을 import 합니다(`app/features/home/__init__.py` 참고).

**2. `main.py` 에 라우터 등록** (직접 편집)

```python
# main.py
from app.features import blog, home, reply, sns, user, <name>   # ← import 추가

app.include_router(<name>.router, prefix="/api")   # ← 취합 한 줄 추가
```

각 기능 `__init__.py` 가 `router` 를 공개하므로 `main.py` 가 명시 `include_router` 로 취합합니다. **모델은 `models_registry`(SSOT)가 `app/features/<name>/models/models.py` 를 자동 수집**하므로 `Base.metadata` 등록에 별도 편집이 필요 없습니다. Admin 은 `app/features/<name>/admin.py` 에 ModelView 와 `admin_views` 를 만들고, `app/features/admin.py` 의 import 와 `ADMIN_VIEWS` 에 한 줄씩 더합니다.

**3. 서버 재시작** — 등록한 라우터가 마운트됩니다.

### 개발 체크리스트

- [ ] `main.py` 에 `from app.features import ..., <name>` + `app.include_router(<name>.router, prefix="/api")`
- [ ] `api/routers/router.py` + `v1/` — 엔드포인트 정의
- [ ] `models/models.py` — SQLAlchemy ORM 모델 (`__init__.py` 에서 import → 자동 수집)
- [ ] `repositories/` — BaseRepository 확장
- [ ] `dependencies/` — 기능 의존성(Service 구성; 쓰기/조회 세션 분리)
- [ ] `services/` — 비즈니스 로직
- [ ] `schemas/` — Pydantic 요청/응답 스키마
- [ ] `tests/` — pytest 테스트
- [ ] Celery 태스크는 중앙 `app/celery/tasks.py` 에 추가 (선택)
- [ ] SQLAdmin 은 기능 `admin.py` 에 ModelView + `admin_views`, `app/features/admin.py` 에 취합 한 줄 (선택)

---

## API 문서

### 접근 URL

| 문서 | URL | 조건 |
|------|-----|------|
| Scalar API 문서 | http://localhost:8000/docs | DEBUG=true |
| OpenAPI JSON | http://localhost:8000/openapi.json | DEBUG=true |
| 관리자 페이지 | http://localhost:8000/admin | ADMIN=true (인증 없음 — 아래 주의) |
| 헬스체크 | http://localhost:8000/health | 항상 |

> **⚠️ `/admin` 에는 인증이 없습니다.** 로그인 화면을 두지 않기로 확정했습니다(`/admin/login` 은 503).
> `ADMIN=true` 이면 자격증명 없이 사용자·게시글·댓글·접속로그의 조회·수정·삭제와 CSV 내보내기가
> 가능합니다(비밀번호 해시만 제외). 기본값이 `true` 인 것은 **개발 편의를 우선한 의도된 선택**입니다.

#### 운영 배포 체크리스트 — 앱이 막아주지 않습니다

**확정된 정책(2026-08-12): 앱에 운영 강제 차단을 넣지 않습니다.** `ENV=production` 과
`ADMIN=true` 를 함께 줘도 기동은 성공합니다 — 이 조합을 거부하는 설정 검증은 **일부러
두지 않았습니다.** 개발 기본값을 그대로 두는 대신, 차단 책임을 배포 쪽에 둡니다.
따라서 아래 세 가지는 **사람이 확인해야 합니다.**

| # | 확인 | 빠뜨리면 |
|---|---|---|
| 1 | 운영·스테이징에 **`ADMIN=false` 를 명시적으로** 넘겼는가 | 기본값이 `true` 라 관리 화면이 열립니다 |
| 2 | 외부 노출이 필요한 컨테이너가 아니면 **`SERVER_HOST=127.0.0.1`** 인가 | 기본값 `0.0.0.0` 이라 네트워크에 바인딩됩니다 |
| 3 | 리버스 프록시·방화벽에서 **`/admin` 을 차단**했는가 | 위 둘이 뚫리면 마지막 방어선이 없습니다 |

**1과 2는 곱해집니다.** `ADMIN=true` 하나만으로는 로컬 접근이고, `SERVER_HOST=0.0.0.0`
하나만으로는 공개 API 노출입니다. **둘이 겹치면 인증 없는 관리 화면이 네트워크에 열립니다.**
기본값이 각각 `true` 와 `0.0.0.0` 이므로, 아무것도 설정하지 않은 배포가 정확히 그 상태입니다.

### 현재 구현된 API

> 아래는 `app.openapi()` 로 실측한 전량입니다 — **18 경로 / 30 오퍼레이션**.
> 새 라우트를 추가하면 이 표도 갱신하세요(`tests/test_route_inventory.py` 가 경로 목록을 고정합니다).

#### 콘텐츠 기능 — blog · reply · sns

세 기능이 같은 CRUD 형태를 공유합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/blog/posts` | 게시글 목록 (페이지네이션) |
| POST | `/api/v1/blog/posts` | 게시글 생성 |
| GET | `/api/v1/blog/posts/{post_id}` | 게시글 단건 |
| PATCH | `/api/v1/blog/posts/{post_id}` | 게시글 부분 수정 |
| DELETE | `/api/v1/blog/posts/{post_id}` | 게시글 삭제 |
| GET · POST | `/api/v1/reply/replies` | 댓글 목록 · 생성 |
| GET · PATCH · DELETE | `/api/v1/reply/replies/{reply_id}` | 댓글 단건 · 수정 · 삭제 |
| GET · POST | `/api/v1/sns/posts` | SNS 게시글 목록 · 생성 |
| GET · PATCH · DELETE | `/api/v1/sns/posts/{post_id}` | SNS 게시글 단건 · 수정 · 삭제 |

#### 사용자 — user

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET · POST | `/api/v1/user/users` | 사용자 목록 · 생성 |
| GET · PATCH · DELETE | `/api/v1/user/users/{user_id}` | 사용자 단건 · 수정 · 삭제 |

#### 인증 — auth

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/v1/auth/register` | 회원 가입 (JSON) |
| POST | `/api/v1/auth/login` | 로그인 — **form-urlencoded** |
| POST | `/api/v1/auth/refresh` | 액세스 토큰 재발급 (JSON) |
| GET | `/api/v1/auth/me` | 내 정보 (Bearer) |

> 요청·응답 형식과 토큰 정책은 [인증 (JWT)](#인증-jwt) 절을 참고하세요.

#### 접속 로그 — home

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/home/access-logs` | 접속 로그 목록 (페이지네이션) |
| GET | `/api/v1/home/access-logs/recent` | 최근 접속 로그 |
| GET | `/api/v1/home/access-logs/by-ip/{ip_address}` | IP별 접속 로그 |
| GET | `/api/v1/home/access-logs/by-user/{user_id}` | 사용자별 접속 로그 |
| GET | `/api/v1/home/access-logs/stats` | 접속 통계 |

#### 그 외

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/health` | 헬스체크 — DB 를 건드리지 않아 항상 응답 |

---

## 참고 자료

- [FastAPI 공식 문서](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 문서](https://docs.sqlalchemy.org/en/20/)
- [Pydantic v2 문서](https://docs.pydantic.dev/latest/)
- [How to structure your FastAPI projects](https://medium.com/@amirm.lavasani/how-to-structure-your-fastapi-projects-0219a6600a8f)

---

## 라이선스

MIT License
