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
- [테스트와 검수](#테스트와-검수)
- [환경 설정](#환경-설정)
- [로깅 시스템](#로깅-시스템)
- [기동과 종료](#기동과-종료)
- [접속 로그 미들웨어](#접속-로그-미들웨어)
- [인증 (JWT)](#인증-jwt)
- [신규 기능 개발 가이드](#신규-기능-개발-가이드)
- [API 문서](#api-문서)

---

## 함께 보는 문서

| 문서 | 언제 읽나 |
|---|---|
| [서버 수명주기 HTML 안내서](./docs/guides/server-lifecycle-guide.html) | `.env` 설정부터 등록·Redis·DB·요청·종료까지 실제 호출 순서를 추적할 때 |
| [신규 뷰·테이블 HTML 개발 안내서](./docs/guides/feature-development-guide.html) | MVC 대응·DI·ORM/Raw·트랜잭션·비동기·migration·테스트를 따라 개발할 때 |
| [QUICKSTART](./docs/guides/QUICKSTART.md) | Redis만 준비해 30초 안에 앱을 띄워보고 싶을 때 |
| [ARCHITECTURE](./docs/guides/ARCHITECTURE.md) | 폴더 분류·라우터 배선·트랜잭션 경계의 근거를 볼 때 |
| **[ORM/Raw 워크플로우 개발 지침서](./docs/guides/ORM-RAW-WORKFLOW.md)** | **ORM 과 Raw SQL 중 무엇을 언제 쓰고, 각각 어떤 순서로 만드는지 배울 때** |
| [로깅과 종료](./docs/guides/LOGGING-AND-SHUTDOWN.md) | 로그가 왜 큐를 거치는지, 종료 순서를 왜 건드리면 안 되는지 알아야 할 때 |

지침서는 두 방식을 **같은 시나리오로 끝까지** 따라갑니다 — §3 ORM(상품 CRUD),
§4 Raw(일별 매출 리포트), §6 Raw SQL 보안 규칙, §7 트랜잭션 지침, §10 코드 리뷰
체크리스트. 아래 [핵심 패턴](#핵심-패턴)이 요약이라면 지침서는 실습 순서입니다.

---

## 개요

이 프로젝트는 FastAPI 기반의 확장 가능한 백엔드 애플리케이션 템플릿입니다.

### 주요 특징

- **계층 분리 아키텍처**: Router → Service → Repository → Database
- **명시적 트랜잭션 경계**: 기능 의존성(`get_<name>_service`)은 Service 구성만 담당하고, 커밋은 **쓰기 핸들러 본문**이 `await service.commit()` 로 수행(UnitOfWork 미사용)
- **읽기/쓰기 세션 분리**: 조회 전용 의존성(`get_<name>_service_readonly`)은 `get_read_only_db_session` 을 받아 커밋하지 않음 — 예외 시 세션 teardown이 롤백
- **인증(JWT)**: OAuth2 Password 플로우 + JWT access/refresh 토큰, bcrypt 비밀번호 해시 (`auth` 기능, `app/utils/authenticator/`)
- **ORM / Raw SQL 두 가지 Repository**: `BaseRepository`(ORM)와 `RawRepositoryBase`(집계·리포트).
  참조 예제가 나란히 있습니다 — `app/features/catalog/`(ORM), `app/features/reports/`(Raw)
- **유연한 설정**: Pydantic Settings 기반 환경 변수 관리
- **구조화된 로깅**: 큐 기반 비차단 핸들러 → stdout/stderr (파일 로그 없음)
- **검증된 종료 절차**: background task → Redis → DB 커넥션 → 로그 순서로 정리하며, 정상 종료·
  startup 실패·취소·`docker stop`(SIGTERM) **모두**에서 끝까지 실행됩니다.
  실제 서버 프로세스를 띄우는 통합 테스트가 이 순서를 고정합니다
  ([상세](./docs/guides/LOGGING-AND-SHUTDOWN.md))
- **API 문서**: Scalar UI 기반 인터랙티브 문서 + OpenAPI 정합성 규칙 테스트
- **관리자 페이지**: SQLAdmin 통합

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| Language | Python 3.12+ |
| Framework | FastAPI 0.141+ |
| ASGI Server | Uvicorn |
| ORM | SQLAlchemy 2.0 (async) |
| Database | MySQL (aiomysql) |
| Validation | Pydantic v2 |
| Migration | Alembic |
| Redis | startup 연결 검증 + Celery 브로커·결과 백엔드 |
| Admin | SQLAdmin |
| API Docs | Scalar |
| Task Queue | Celery + Redis |
| Auth | OAuth2 Password + JWT(PyJWT) + bcrypt |

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
호출합니다(예외 시 `get_writer_db_session` teardown 이 롤백). 조회 엔드포인트는
`get_<name>_service_readonly` 를 써서 `get_read_only_db_session` 을 받고 커밋하지 않습니다.
요청 밖(백그라운드/Celery)에서는 `background_db_session()` 컨텍스트(별도 풀)를 사용해
메인 API 풀 고갈을 방지합니다.

---

## 프로젝트 구조

> 상세한 아키텍처 설명은 **[docs/guides/ARCHITECTURE.md](docs/guides/ARCHITECTURE.md)** 를 참고하세요.

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
│   │   ├── resources.py         # 프로세스 수명 자원의 생성·해제 단일 지점 (lifespan)
│   │   ├── exception.py         # 공통 예외 계층
│   │   ├── tags_metadata.py     # OpenAPI 태그 설명
│   │   ├── db/                  # 세션·라우팅·모델 등록
│   │   │   ├── session.py       # 엔진, get_writer_db_session / get_read_only_db_session, background_db_session
│   │   │   ├── router.py        # 읽기/쓰기 라우팅 (RoutingSession)
│   │   │   └── models_registry.py  # 모델 import 단일 지점 (SSOT)
│   │   ├── models/models_base.py   # Base + UUID·Timestamp Mixin, UUIDTimestampModel
│   │   ├── repositories/        # BaseRepository(ORM) + RawRepositoryBase(Raw SQL)
│   │   ├── services/            # BaseService
│   │   └── middlewares/         # CORS, UserInfo, AccessLogSink, background_tasks
│   │
│   ├── celery/                  # 중앙 Celery 앱 + tasks.py + run_async 브릿지
│   └── utils/                   # logs(구조화 로깅) · authenticator(JWT·bcrypt) ·
│                                #   pagination · validators
│
├── conftest.py                  # pytest 전역 옵션 (--mysql-required) — 루트여야 인식된다
├── tests/                       # 횡단 테스트 — core 계약·배선·교차 기능
│   ├── core/                    # 설정 계약, 자원 lifespan, admin 뷰 정책, 마이그레이션 등
│   ├── utils/                   # 로깅·인증·페이지네이션 유틸
│   ├── integration/             # 실제 프로세스·DB 대상
│   │                            #   test_uvicorn_lifecycle.py  실제 서버 기동·종료 검증
│   │                            #   test_mysql_raw_sql.py      MySQL 8.4 (없으면 skip)
│   └── test_*.py                # 라우터/admin 배선, 응답 직렬화, OpenAPI 계약 등
│
├── migrations/                  # Alembic (env.py 가 import_all_models() SSOT 로 메타데이터 수집)
├── .github/workflows/ci.yml     # CI 게이트 (ruff · format · mypy 콜드캐시 · pytest · bandit · alembic)
├── scripts/review_gate.py       # 검수 게이트 12종 — 아래 [테스트와 검수] 참고
├── compose.test.yaml            # 통합 테스트용 MySQL 8.4 (호스트 포트 3308) · Redis 7 (6379)
├── docs/
│   ├── guides/                  # 현행 사용자·개발자 가이드
│   │   ├── ARCHITECTURE.md      # 아키텍처 공식 문서 (SSOT)
│   │   ├── QUICKSTART.md        # 최소 실행 경로
│   │   ├── ORM-RAW-WORKFLOW.md  # ORM/Raw 워크플로우 개발 지침서
│   │   └── LOGGING-AND-SHUTDOWN.md # 로깅·종료 구조 설명
│   ├── specs/orm-raw-repository/ # ORM/Raw 요구명세·개발계획·지침 원본 (착수 기준선)
│   └── crp/groups/              # 작업 그룹별 설계 기준선·결함 원장
└── media/ static/ poc/ logs/    # 런타임·예약 디렉터리 (.gitkeep 만 추적)
                                 #   logs/ 는 파일 로깅 제거 후 남은 예약 자리다
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
| `app/core/db/session.py` | SQLAlchemy 엔진, 세션 팩토리, 커넥션 풀, `background_db_session` |
| `app/core/resources.py` | 프로세스 수명 자원의 생성·해제 **단일 지점**. 자원마다 async context manager 를 두고 획득 순서대로 중첩해 정리 순서를 코드로 보이게 합니다 → [로깅과 종료](./docs/guides/LOGGING-AND-SHUTDOWN.md) |
| `app/utils/logs/` | 큐 기반 비차단 로깅 + listener 수명 관리(`atexit`·신호 핸들러). **여기 손대기 전에 위 문서를 읽으세요** |
| `conftest.py` (루트) | pytest 전역 옵션. `--mysql-required` 가 통합 테스트의 skip 을 실패로 바꿉니다 |
| `app/features/<name>/dependencies/` | 기능 의존성 — Service 구성(쓰기용 `get_writer_db_session` / 조회용 `get_read_only_db_session`). 커밋은 핸들러가 수행 |
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
| **Dependency** | 세션 주입(쓰기 `get_writer_db_session` / 조회 `get_read_only_db_session`) → `Service(session)` 구성 후 **반환**(`yield` 아님) | 비즈니스 로직·커밋 |
| **Service** | `BaseService` 상속, `self.session`/Repository로 데이터 접근·비즈니스 로직 | 커밋 시점 결정(핸들러가 담당) |
| **Repository** | `BaseRepository`(ORM) 또는 `RawRepositoryBase`(Raw SQL) 상속, 쿼리 캡슐화, Eager Loading 조회 명시 | 비즈니스 로직·커밋 |

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
7. 의존성 teardown — 예외로 빠져나갔다면 get_writer_db_session 이 rollback()
```

### 코드 예시

```python
# dependencies — Service 구성만 담당(커밋하지 않는다)
async def get_blog_service(
    session: AsyncSession = Depends(get_writer_db_session),          # 쓰기용
) -> BlogService:
    return BlogService(session)


async def get_blog_service_readonly(
    session: AsyncSession = Depends(get_read_only_db_session),     # 조회용 — 커밋 없음
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
- **예외**: 뷰/Service 에서 예외 발생 → 커밋이 실행되지 않고 `get_writer_db_session` teardown 이 `session.rollback()`.
- **요청 밖(Celery/백그라운드)**: `async with background_db_session() as session:` 컨텍스트로 커밋/롤백을 직접 관리(별도 풀).

---

## 핵심 패턴

### 1. Repository 패턴

데이터 접근 로직을 캡슐화하여 비즈니스 로직과 분리합니다. 접근 방식에 따라 상속할 Base 가
두 개이고, **둘 사이에 상속 관계는 없습니다**.

#### 1-1. ORM — `BaseRepository`

공개 계약은 **최소 CRUD 8개**입니다. 여기에 없는 조회는 기능 Repository 가 SQLAlchemy 로
직접 씁니다 — Base 에 문자열 컬럼명을 받는 범용 필터를 두면 오타가 실행 시점에만 드러납니다.

```python
# app/core/repositories/repository_base.py (+ crud_base.py)
class BaseRepository(CRUDBase[ModelType], Generic[ModelType, PrimaryKeyT]):
    """모델 하나에 대한 최소 공개 CRUD."""

    model: type[ModelType]

    async def create(self, data: dict[str, Any]) -> ModelType: ...
    async def get_by_id(self, pk: PrimaryKeyT) -> ModelType | None: ...
    async def get_by_id_or_raise(self, pk: PrimaryKeyT) -> ModelType: ...
    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[ModelType]: ...
    async def count(self, **filters: Any) -> int: ...
    async def exists(self, pk: PrimaryKeyT) -> bool: ...
    async def update_by_id(self, pk: PrimaryKeyT, data: dict[str, Any]) -> ModelType | None: ...
    async def delete_by_id(self, pk: PrimaryKeyT) -> bool: ...
```

- `PrimaryKeyT` 는 기본값이 `str`(문자열 UUID)이라 `BaseRepository[Post]` 처럼 생략할 수 있습니다.
- 모든 공개 경로가 **같은 예외 변환**을 지납니다: `IntegrityError` → `DuplicateException`,
  그 밖의 `SQLAlchemyError` → `DatabaseException`. 응답 `detail` 에는 모델명·연산명만 담고
  드라이버 원문은 넣지 않습니다 — 무결성 위반 메시지에는 **위반한 값 자체**(중복된 이메일
  등)가 들어 있어 그대로 유출됩니다.
- `get_all` / `update` / `delete` / `get_one` 은 이전 이름의 **얇은 별칭**으로만 남아 있습니다.
  새 코드는 위 8개를 씁니다.

```python
# 기능별 Repository 확장 — Base 에 없는 조회는 여기서 명시적으로
class ProductRepository(BaseRepository[Product, str]):
    model = Product

    async def list_active(self, *, skip: int = 0, limit: int = 100) -> Sequence[Product]:
        statement = (
            select(Product)
            .where(Product.is_active.is_(True))       # 문자열 컬럼명이 아니라 속성으로
            .order_by(Product.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db_session.execute(statement)
        return result.scalars().all()
```

#### 1-2. Raw SQL — `RawRepositoryBase`

집계·리포트처럼 ORM 으로 표현할 이유가 없는 질의는 `text()` 로 직접 씁니다.

```python
# app/core/repositories/raw_repository_base.py (+ raw_crud_base.py)
class RawRepositoryBase(RawCRUDBase):
    async def fetch_one(self, statement, params=None, *, query_name) -> RowMapping | None: ...
    async def fetch_all(self, statement, params=None, *, query_name) -> Sequence[RowMapping]: ...
    async def fetch_scalar(self, statement, params=None, *, query_name) -> Any: ...
    async def execute(self, statement, params=None, *, query_name) -> int: ...
```

```python
_DAILY_SALES_SQL = text("""
    SELECT DATE(o.created_at) AS sales_date,
           COUNT(*)           AS order_count,
           COALESCE(SUM(o.total_amount), 0) AS gross_amount
      FROM sales_orders AS o
     WHERE o.created_at >= :start_at AND o.created_at < :end_at    -- named bind
     GROUP BY DATE(o.created_at)
     ORDER BY sales_date ASC
""")
```

- **값은 전부 bind parameter** 입니다. 문자열 포매팅으로 SQL 을 만들지 않습니다.
- 값으로 바인딩할 수 없는 자리(컬럼명·정렬 방향)는 `resolve_identifier()` /
  `resolve_sort_direction()` 로 **허용 목록에 대조**해 고릅니다.
- 반환은 `RowMapping` 이고, Service 가 Pydantic DTO 로 검증해 내보냅니다. 집계 **결과** 전용
  ORM 모델은 만들지 않습니다.
- `query_name` 이 필수 키워드인 이유는 관측 때문입니다 — 느린 질의를 SQL 본문 없이
  이름과 소요시간만으로 식별합니다(로그에 파라미터를 남기지 않습니다).

> 실물 비교: `app/features/catalog/`(ORM) 와 `app/features/reports/`(Raw). 두 기능은
> Repository 구현만 다르고 Dependency·Service·트랜잭션 경계·응답 검증이 동일합니다.
>
> 두 방식을 **처음부터 끝까지 만들어 보려면**
> [ORM/Raw 워크플로우 개발 지침서](./docs/guides/ORM-RAW-WORKFLOW.md)
> 를 따라가세요. 위 코드가 어떤 순서로 나왔는지가 그 문서에 있습니다.

### 2. 트랜잭션 경계 — 쓰기 핸들러 (UnitOfWork 대체)

UnitOfWork 대신 **쓰기 핸들러**가 커밋 시점을 쥡니다. 기능 의존성은 세션으로 Service를
구성해 넘겨주기만 하고, 커밋은 하지 않습니다. 커밋이 응답 생성보다 먼저 끝나므로
커밋 실패가 성공 응답으로 둔갑하지 않습니다.

```python
# app/features/blog/dependencies/blog_dependencies.py — 구성만 한다
async def get_blog_service(
    session: AsyncSession = Depends(get_writer_db_session),          # 쓰기용
) -> BlogService:
    return BlogService(session)


async def get_blog_service_readonly(
    session: AsyncSession = Depends(get_read_only_db_session),     # 조회용
) -> BlogService:
    return BlogService(session)


# app/features/blog/api/routers/v1/blog.py — 커밋은 여기서
async def create_post(
    payload: PostCreate,
    service: BlogService = Depends(get_blog_service),
) -> PostResponse:
    post = await service.create_post(payload)
    await service.commit()          # 예외 시 get_writer_db_session teardown 이 롤백
    return PostResponse.model_validate(post)
```

- 조회 엔드포인트는 `_readonly` 의존성을 써서 `get_read_only_db_session` 을 받습니다. 불필요한
  COMMIT 왕복이 사라지고, `DB_ROUTER_ENABLED` 가 켜지면 replica 로 라우팅됩니다.
  읽기 핸들러가 몰래 쓰기를 시도하면 `ReadOnlyRoutingError` 로 즉시 실패합니다.
- 요청 밖(Celery/백그라운드)에서는 `async with background_db_session() as session:` 컨텍스트로
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
        logs = await self.repository.list(skip=skip, limit=limit)
        total = await self.repository.count()
        return logs, total
```

### 4. N+1 문제 해결

관계를 함께 적재하는 조회는 **기능 Repository 가 직접** 씁니다. Base 에 문자열 관계명을
받는 범용 메서드(`get_all_with(relations=[...])`)를 두지 않는 이유는, 오타나 이름이 바뀐
관계가 **실행 시점에야** 드러나기 때문입니다. SQLAlchemy 속성으로 쓰면 정적 검사에 걸립니다.

```python
# 문제: N+1 쿼리 발생
for user in users:
    print(user.posts)  # 각 사용자마다 추가 쿼리 발생


# 해결: 기능 Repository 에 Eager Loading 조회를 명시한다
class UserRepository(BaseRepository[User]):
    model = User

    async def list_with_posts(self, *, skip: int = 0, limit: int = 100) -> Sequence[User]:
        statement = (
            select(User)
            .options(selectinload(User.posts))   # 관계를 속성으로 지정
            .offset(skip)
            .limit(limit)
        )
        result = await self.db_session.execute(statement)
        return result.scalars().all()
```

| 전략 | 발행 쿼리 | 적합한 경우 |
|---|---|---|
| `selectinload` | `SELECT ... WHERE id IN (...)` | 1:N — 대부분의 경우 권장 |
| `joinedload` | `LEFT OUTER JOIN` | 1:1, 또는 항상 함께 쓰는 소수 행 |
| `subqueryload` | 서브쿼리 | 중첩이 깊은 관계 |

---

## 시작하기

> **처음이라면 [docs/guides/QUICKSTART.md](docs/guides/QUICKSTART.md) 부터.** Redis만 준비해 30초 만에
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
# 둘 중 아무거나 쓰면 됩니다.
uv run python main.py                                        # .env 의 HOST/PORT/DEBUG 를 그대로 사용
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000  # uvicorn 표준 CLI
```

> 두 명령 모두 정상 동작합니다. 오류와 traceback 도 **똑같이** 출력됩니다 — 로깅
> listener 를 lifespan 이 아니라 프로세스가 소유하기 때문입니다(ADR-018).
> 차이는 **uvicorn 자신의 로그 포맷 하나뿐**입니다: `python main.py` 는 프로젝트 포맷
> (`[app=uvicorn]` 라벨)으로, `uvicorn main:app` 은 uvicorn 기본 포맷으로 나갑니다.
> 앞의 명령이 `run_server()` 를 거치며 `uvicorn.run(log_config=...)` 을 넘기기 때문입니다
> (ADR-020).

### 6. 접속

- API 서버: http://localhost:8000
- API 문서: http://localhost:8000/docs
- 관리자 페이지: http://localhost:8000/admin
- 헬스체크: http://localhost:8000/health

---

## 테스트와 검수

### 실행

```bash
# 단위 테스트 — 외부 인프라 없이 실행됩니다 (MySQL 테스트는 skip)
uv run pytest -q

# 전량 — MySQL 8.4 컨테이너를 먼저 띄웁니다 (호스트 포트 3308)
docker compose -f compose.test.yaml up -d --wait
uv run pytest -q
docker compose -f compose.test.yaml down -v
```

| 구분 | 개수 | 비고 |
|---|---:|---|
| 단위·계약·통합(프로세스) | 409 | 외부 인프라 불필요 |
| MySQL 8.4 대상 (`-m mysql`) | 8 | 컨테이너 필요 |
| **합계** | **417** | failed 0 · skipped 0 |

### `--mysql-required` — skip 을 실패로 바꿉니다

MySQL 이 없으면 통합 테스트는 skip 됩니다. 문제는 **skip 이 결과만 보면 초록으로
읽힌다**는 것입니다. CI 에서 컨테이너가 안 떴는데 "통과" 로 보이면 *"돌았는데 통과"* 와
*"안 돌았다"* 가 구분되지 않습니다.

```bash
uv run pytest -q -m mysql --mysql-required   # DB 에 닿지 못하면 skip 이 아니라 실패
```

통합 검증을 근거로 쓰는 자리(릴리스 판정·수렴 판정)에서는 항상 이 옵션을 붙이세요.

### 검수 게이트

```bash
uv run python scripts/review_gate.py          # 전체
uv run python scripts/review_gate.py --fast   # 테스트 제외
```

검사 **12종** — 도구 4종(pytest · ruff check · ruff format · mypy)과 프로젝트 규칙 8종입니다.

| 검사 | 무엇을 보나 |
|---|---|
| 계층 불변식 (INV-1·2·5) | View 가 SQL/세션을 직접 다루는지, Repository/Dependency 가 커밋하는지, Raw Base 가 ORM Base 를 상속하는지 — **AST 로** 확인 |
| 공개 API 불변 (INV-11) | `baseline/openapi.json` 대비 경로·상태 코드가 사라지거나 바뀌었는지 |
| path operation (INV-10) | 전 엔드포인트가 `async def` 이고 요청 루프에서 동기 I/O 를 하지 않는지 |
| MySQL 포트 단일 출처 | 포트 값이 여러 곳에 흩어졌는지 |
| 문서 인용 커밋 도달성 | 문서가 인용한 커밋 해시가 실재하는지 |
| 인용 요구 ID 실재 | 코드·문서가 인용한 REQ/ADR ID 가 선언돼 있는지 |
| 취소·프로세스 종료 테스트 실재 | 종료 계약을 지키는 테스트 5건이 **삭제·개명되지 않았는지** |
| charter ↔ 수렴 선언 정합 | 인수 기준이 열린 채 "수렴" 을 선언하지 않았는지 |

마지막 두 검사는 *"테스트나 기준이 조용히 사라지는 것"* 을 막습니다. 이 프로젝트에서
실제로 일어났던 일이라 기계가 봅니다.

### CI

`.github/workflows/ci.yml` 이 같은 검사를 돌립니다 — ruff(lint·format) · mypy(콜드 캐시) ·
bandit(MEDIUM 이상) · pytest · **SKIP·xfail 0건 확인** · alembic 단일 head.

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
| `LOG_CONSOLE_ENABLED` | `true` | 콘솔 로그 활성화 (로그는 파일이 아닌 stdout/stderr 로 나갑니다) |
| `LOG_SQL_ECHO_ENABLED` | `false` | SQL·바인딩 값 로깅. **운영에서 켜지 마세요** |
| `DB_ROUTER_ENABLED` | `false` | 읽기/쓰기 세션 라우팅 (기본은 단일 엔진) |

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
┌─────────────────────────────────────────────────────────────┐
│              BoundedQueueHandler (put_nowait)                │
│   요청 스레드는 큐에 넣기만 하고 즉시 돌아온다 — I/O 로 막지 않는다  │
└─────────────────────────────────────────────────────────────┘
                              ↓  (별도 스레드가 소비)
┌─────────────────────────────────────────────────────────────┐
│                        QueueListener                         │
└─────────────────────────────────────────────────────────────┘
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
    console (stdout)                 error_console (stderr)
    INFO+ / 색상                      ERROR+ (staging·production)
```

**로그를 파일에 쓰지 않습니다.** 컨테이너에서는 stdout/stderr 가 표준 수집 경로이고,
파일로 쓰면 로테이션·디스크 관리·수집기 연동이 전부 애플리케이션 책임이 됩니다.
파일이 필요하면 수집 계층에서 처리하세요.

**큐가 가득 차면** ERROR·CRITICAL 은 stderr 로 직접 흘리고(로깅 API 를 다시 타지 않습니다 —
재진입하면 같은 큐에서 다시 막힙니다), 그 아래 레벨은 버리고 누락 사실만 주기적으로 알립니다.
로깅이 요청 처리를 막지 않는 것이 우선입니다.

### listener 의 수명 — 손대기 전에 읽으세요

큐 구조에는 반드시 알아야 할 성질이 하나 있습니다.

> **`logger.info()` 가 성공했다고 그 줄이 출력된 것은 아닙니다.** 큐에 들어가 있을 뿐이고,
> listener 가 꺼내 쓰기 전에 프로세스가 죽으면 그 줄은 영원히 사라집니다.

그래서 listener 의 수명은 **FastAPI lifespan 이 아니라 프로세스**가 소유합니다.
lifespan 에서 listener 를 멈추면, 그 **뒤에** uvicorn 이 남기는 최종 로그와 startup 실패
traceback 이 소비자 없는 큐에 갇혀 사라집니다. 실제 증상은 *"DB 가 꺼진 채 서버를 띄우면
오류 원인이 한 글자도 안 나온다"* 였습니다.

- lifespan 은 listener 를 **멈추지 않습니다.** 대신 종료 맨 끝에서 **쌓인 로그가 다 나갈
  때까지 기다립니다**(멈추기가 아니라 기다리기입니다).
- 실제 정지는 `atexit` 훅과 `SIGTERM`/`SIGBREAK` 핸들러가 합니다. `docker stop` 은
  `atexit` 이 실행되지 않는 경로라 신호 핸들러가 따로 필요합니다.

⚠️ **`app/core/resources.py` 에 listener 정지 코드를 넣지 마세요.** 왜 그런지와 각 장치가
무엇을 막는지는 **[로깅과 종료](./docs/guides/LOGGING-AND-SHUTDOWN.md)** 에 전부 적어 뒀습니다.

### 환경 변수 설정

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `LOG_CONSOLE_ENABLED` | `true` | 콘솔(stdout/stderr) 로그 출력 활성화 |
| `LOG_SQL_ECHO_ENABLED` | `false` | **SQL 과 바인딩된 값**을 로그로 내보낼지. 로컬 디버깅 전용 |
| `LOG_LEVEL` | - | 전역 로그 레벨 (미설정 시 DEBUG 모드에 따라 자동 결정) |
| `LOG_CONSOLE_LEVEL` | - | 콘솔 로그 레벨 (미설정 시 자동 결정) |
| `LOG_CONSOLE_FORMAT` | (아래 포맷) | 콘솔 로그 포맷 문자열 |
| `LOG_DATE_FORMAT` | - | 시각 포맷 |

> **`LOG_SQL_ECHO_ENABLED` 를 운영에서 켜지 마세요.** 켜면 SQLAlchemy 와 DB 드라이버가
> 실행 SQL 과 **바인딩된 파라미터 값**을 그대로 기록합니다. 그 값에는 비밀번호 해시·토큰·
> 검색어가 들어 있고, 로그는 대개 외부 수집기로 흘러갑니다. 기본값이 `false` 인 이유이고,
> 꺼져 있으면 WARNING 미만의 SQL 로그는 레벨과 무관하게 차단됩니다(장애는 계속 보입니다).

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

# app/features/catalog/services/catalog_service.py
logger = get_logger("product_service")
logger.info(f"상품 생성 완료: {product.id}")

# app/features/user/services/user_service.py
logger = get_logger("user_service")
logger.info(f"사용자 로그인: {user.email}")

# 출력 예시:
# [2024-01-15 10:30:00] INFO     [product_service:create:45] 상품 생성 완료: abc123
# [2024-01-15 10:30:01] INFO     [user_service:login:78] 사용자 로그인: user@example.com
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

## 기동과 종료

### 실행 명령 두 가지

```bash
uv run python main.py                                        # run_server() 경유
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000  # uvicorn 표준 CLI
```

둘 다 정상 동작하며 **오류와 traceback도 동일하게 출력**됩니다. 차이는 uvicorn 자신의
로그 포맷 하나뿐입니다.

| | `python main.py` | `uvicorn main:app` |
|---|---|---|
| uvicorn 로그 | 프로젝트 포맷 + `[app=uvicorn]` | uvicorn 기본 (`INFO:     …`) |
| 앱 로그 | 프로젝트 포맷 | 프로젝트 포맷 |
| 오류·traceback | 전부 출력 | 전부 출력 |

앞의 명령이 `run_server()` 를 거치며 `uvicorn.run(log_config=...)` 으로 프로젝트 설정을
넘기기 때문입니다. 앱 `dictConfig` 에 uvicorn 로거를 심는 방법도 있지만, 그건 uvicorn 내부
실행 순서에 기대는 것이라 코드만 봐서는 검증할 수 없어 채택하지 않았습니다.

### 종료 순서

자원은 **획득의 역순**으로 정리됩니다. 순서를 강제하는 코드는 없습니다 —
중첩 컨텍스트가 곧 순서입니다.

```python
# app/core/resources.py
async with _log_queue(), _database(app), _redis(app), _background_tasks():
    ...
# 정리: background drain → Redis close → DB dispose → 로그 큐 flush
```

```
[shutdown] 애플리케이션 요청 처리 자원 해제 시작
[shutdown] background task 정리 완료
[shutdown] Redis client 정리 완료
[dispose_engine] Disposing 2 database engine(s)...
[shutdown] DB engine 정리 완료
[shutdown] 애플리케이션 요청 처리 자원 해제 완료     ← 정리가 끝까지 갔다는 확인선
Application shutdown complete                        (uvicorn)
Finished server process                              (uvicorn)
[log-lifecycle] stop 완료                            ← listener 정지
```

자원을 쓰는 주체(background task)를 먼저 멈춘 뒤 Redis와 DB 커넥션 풀을 닫고, 로그 정리는 언제나
**가장 마지막**입니다.

| 자원 | 예산 |
|---|---|
| background task drain | 5초 |
| Redis client close | 5초 |
| DB engine dispose | 10초 |
| 로그 큐 flush | 2초 |
| **전체 상한** | **20초** |

### 이 순서는 실제 프로세스로 검증됩니다

`tests/integration/test_uvicorn_lifecycle.py` 가 실제 서버를 띄우고 운영과 같은 종료
신호(Windows `CTRL_BREAK`, POSIX `SIGTERM`)를 보낸 뒤, 병합된 단일 출력에서 위 순서를
확인합니다. startup 실패 시 traceback 이 실제로 출력되는지도 함께 봅니다.

lifespan 을 직접 호출하는 단위 테스트로는 이 계열 결함이 **보이지 않습니다** — 문제가 사는
곳이 lifespan 바깥(프로세스 종료·신호 처리·uvicorn 내부)이기 때문입니다.

> 각 장치가 무엇을 막는지는 **[로깅과 종료](./docs/guides/LOGGING-AND-SHUTDOWN.md)** 를 보세요.

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

2. **분리된 커넥션 풀**: 접속 로그 sink는 `background_db_session()`(별도 백그라운드 풀)을 사용하여 메인 API 풀 고갈을 방지합니다.

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

## 신규 기능 개발 가이드

> 상세 아키텍처 및 각 파일의 역할은 **[docs/guides/ARCHITECTURE.md](docs/guides/ARCHITECTURE.md)** 를 참고하세요.

새 기능은 `app/features/<name>/` vertical slice 를 만든 뒤 **`main.py` 에 라우터를 명시 등록**합니다.
등록을 빠뜨리면 라우터가 연결되지 않습니다.

### 최소 절차 (3단계)

**1. `app/features/<name>/` 생성 + 코드 작성** (`api/routers/`, `models/`, `schemas/`, `repositories/`, `services/`, `dependencies/`)
`__init__.py` 는 `router` 를 공개하고 `models` 모듈을 import 합니다(`app/features/home/__init__.py` 참고).

**2. `main.py` 에 라우터 등록** (직접 편집)

```python
# main.py
from app.features import blog, catalog, home, reply, reports, sns, user, <name>  # ← 추가

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

> 아래는 `app.openapi()` 로 실측한 전량입니다 — **23 경로 / 38 오퍼레이션**.
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

#### 데이터 접근 참조 예제 — catalog(ORM) · reports(Raw SQL)

같은 앱 안에서 두 방식을 나란히 보여주는 예제입니다. 자세한 사용 기준은
[ORM/Raw 워크플로우 개발 지침서](./docs/guides/ORM-RAW-WORKFLOW.md)에
있습니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET · POST | `/api/v1/catalog/products` | 상품 목록 · 생성 — **ORM Repository** |
| GET · PATCH · DELETE | `/api/v1/catalog/products/{product_id}` | 상품 단건 · 수정 · 삭제 |
| GET | `/api/v1/reports/sales/daily` | 일별 매출 집계 — **Raw SQL Repository** |
| POST | `/api/v1/reports/sales/daily/snapshots` | 일별 매출 스냅샷 재적재 (Raw 쓰기 경로) |

#### 그 외

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/health` | **liveness** — 프로세스 생존만 확인. 외부 연결을 검사하지 않는다 |
| GET | `/ready` | **readiness** — writer DB 에 `SELECT 1`. 실패·지연 시 503 |

> `/health` 와 `/ready` 를 구분하는 이유: `/health` 가 DB 를 검사하면 DB 가 잠깐 흔들릴 때
> 멀쩡히 살아 있는 프로세스가 재시작됩니다. 의존 자원 준비 여부는 `/ready` 로 봅니다.

---

## 참고 자료

- [FastAPI 공식 문서](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 문서](https://docs.sqlalchemy.org/en/20/)
- [Pydantic v2 문서](https://docs.pydantic.dev/latest/)
- [How to structure your FastAPI projects](https://medium.com/@amirm.lavasani/how-to-structure-your-fastapi-projects-0219a6600a8f)

---

## 라이선스

MIT License
