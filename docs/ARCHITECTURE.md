# 아키텍처 문서

이 문서는 프로젝트의 유일한 공식 아키텍처 소스입니다.
코드와 문서 간 불일치가 있으면 코드가 정답이며, 이 문서를 업데이트하세요.

---

## 1. 폴더 분류체계

```
fastapi-default-project-structure/
├── main.py                          # 진입점: 각 앱 router 를 include_router 로 취합 + 앱 설정
├── config.py                        # Pydantic Settings (app/db/cors/log/redis/middleware/timezone)
├── pyproject.toml                   # 의존성 + [tool.uv] package = false
│
├── app/
│   ├── features/                    # 기능 단위 앱
│   │   ├── catalog/                 # 참조 예제 — ORM Repository (상품 CRUD)
│   │   ├── reports/                 # 참조 예제 — Raw SQL Repository (일별 매출 집계)
│   │   ├── home/                    # 예시 앱 — 접속 로그
│   │   │   ├── __init__.py          # router 공개 + models import (admin_views 재노출 금지)
│   │   │   ├── api/routers/
│   │   │   │   ├── router.py        # 앱 루트 라우터 (<name>_router: v1 취합)
│   │   │   │   └── v1/              # 버전별 엔드포인트 (뷰는 HTTP 역할만)
│   │   │   ├── models/              # SQLAlchemy ORM 모델
│   │   │   ├── schemas/             # Pydantic 요청/응답 스키마
│   │   │   ├── services/            # 비즈니스 로직
│   │   │   ├── repositories/        # 데이터 접근 계층
│   │   │   ├── dependencies/        # FastAPI Depends 헬퍼 (Service 구성 — 커밋은 핸들러)
│   │   │   ├── admin.py             # SQLAdmin ModelView + admin_views (모델이 있으면 필수)
│   │   │   ├── exceptions.py        # 기능 예외 (선택)
│   │   │   └── tests/               # 기능 테스트
│   │   └── <name>/                  # 추가 앱은 같은 구조를 따름
│   │
│   ├── core/                        # 프레임워크 인프라 (features 가 의존)
│   │   ├── exception.py             # 공통 예외 계층 + ErrorResponse
│   │   ├── tags_metadata.py         # OpenAPI 태그 메타데이터
│   │   ├── resources.py             # lifespan 자원 관리 (기동 준비·역순 종료)
│   │   ├── db/
│   │   │   ├── session.py           # 엔진, 세션 팩토리, 커넥션 풀, background_db_session
│   │   │   ├── router.py            # 읽기/쓰기 라우팅 (RoutingSession)
│   │   │   └── models_registry.py   # 모델 import 단일 지점 (SSOT)
│   │   ├── models/models_base.py    # Base + UUID·Timestamp Mixin, UUIDTimestampModel
│   │   ├── repositories/
│   │   │   ├── crud_base.py         # ORM 제네릭 CRUD (SQLAlchemy 구문 조립)
│   │   │   ├── repository_base.py   # BaseRepository — ORM 공개 계약(최소 CRUD 8개)
│   │   │   ├── raw_crud_base.py     # Raw SQL 실행·관측 (text() + named bind)
│   │   │   └── raw_repository_base.py # RawRepositoryBase — Raw 공개 계약
│   │   ├── services/services_base.py # BaseService
│   │   └── middlewares/
│   │       ├── cors_middleware.py
│   │       ├── user_info_middleware.py
│   │       ├── background_tasks.py  # 응답 후 태스크 추적 (누수 방지)
│   │       └── access_log_sink.py
│   │
│   ├── celery/                      # 중앙 Celery (기능별 worker/ 미사용)
│   │   ├── app.py                   # Celery 앱 (include=["app.celery.tasks"])
│   │   ├── tasks.py                 # 중앙 태스크 모듈 (모든 기능 백그라운드 작업)
│   │   └── task.py                  # run_async() 동기 브릿지
│   │
│   └── utils/                       # 순수 유틸 (외부·상위 계층 의존 없음)
│       ├── logs/                    # 구조화 로깅 (get_logger, 큐 기반 비차단 핸들러)
│       ├── authenticator/           # 인증 (JWT·bcrypt)
│       ├── pagination/              # 페이지네이션 (순수 dataclass)
│       └── validators.py            # 공통 값 검증
│
├── tests/                           # 횡단 테스트 (core 계약·배선·교차 기능)
│   ├── core/                        # 설정 계약, admin 뷰 정책, 마이그레이션 체인
│   ├── integration/                 # 실제 MySQL 8.4 대상 (@pytest.mark.mysql, 미가용 시 skip)
│   └── utils/                       # 로깅·인증·페이지네이션
│
├── scripts/review_gate.py           # 단계별 결정적 검수 게이트 (정적분석 + 불변식 + API 불변)
├── compose.test.yaml                # 통합 테스트용 MySQL 8.4 (호스트 포트 3308, tmpfs)
├── migrations/env.py                # import_all_models()(SSOT) 로 전 기능 모델 자동 수집
├── .github/workflows/ci.yml         # CI 게이트 (ruff·format·mypy 콜드캐시·pytest·bandit·alembic)
└── docs/
    ├── ARCHITECTURE.md              # ← 이 문서 (아키텍처 SSOT)
    ├── QUICKSTART.md                # 최소 실행 경로
    └── crp/groups/                  # 작업 그룹별 설계 기준선·결함 원장
```

> 기능 테스트는 `app/features/<name>/tests/`, 횡단 테스트는 최상위 `tests/` 에 둡니다.
> `pytest` 가 양쪽을 모두 수집합니다.

### 의존 방향

```
features → core → utils
```

`core`는 `utils`만 알고, `features`는 `core`를 사용합니다.
`core`는 절대로 `features`를 import하지 않습니다(기능 앱이 미들웨어 등에 붙어야 하면
등록 훅으로 연결 — 예: `access_log_sink.register_sink()`).

---

## 2. 표준 FastAPI 배선 (include_router)

라우터 등록에는 자동 스캔이나 중앙 `app/apps.py` SSOT를 사용하지 않습니다.
각 기능 패키지의 `__init__.py`가 하위 뷰 라우터를 취합한 `router`를 공개하고,
`main.py`가 이를 명시적으로 import 해 `include_router`로 최종 취합합니다.
이것이 FastAPI 공식(Bigger Applications) 패턴입니다.

### 2.1 앱 패키지 — `router` 공개

```python
# app/features/<name>/__init__.py
from app.features.<name>.api.routers.router import <name>_router as router
from app.features.<name>.models import models as _models  # noqa: F401 (Base.metadata 등록)

__all__ = ["router"]
```

- `api/routers/router.py`의 `<name>_router`가 `api/routers/v1/*`의 서브라우터를 취합합니다.
- home 은 import 시 `register_sink()`로 access-log sink를 미들웨어에 등록합니다(부수효과).
- SQLAdmin ModelView 는 기능이 소유하고(`admin.py`), `app/features/admin.py` 가 **명시 import** 로 취합합니다 — `getattr` 관용 수집을 쓰지 않으므로 빠지면 기동 시 ImportError 로 터집니다.

### 2.2 `main.py` — 최종 취합 + 앱 설정

```python
from app.features import auth, blog, catalog, home, reply, reports, sns, user

app = FastAPI(...)                        # 인스턴스 + lifespan + 문서 설정
CustomCORSMiddleware(app).configure_cors()
setup_user_info_middleware(app)
_register_exception_handlers(app)         # 4개 글로벌 핸들러

app.include_router(home.router, prefix="/api")   # 기능마다 한 줄
app.include_router(blog.router, prefix="/api")
# ... reply, sns, user, auth, catalog, reports

_add_health_and_docs(app)                 # /health + /ready + Scalar
if app_settings.ADMIN:                    # SQLAdmin
    register_admin(app, engine)           # app/features/admin.py — 조립 진입점
```

라우터·미들웨어·예외 핸들러·문서·lifespan·Admin 등록이 전부 `main.py`에서 일어납니다.
별도의 `create_app()` 팩토리·`bootstrap.py`·`APPS` 목록은 없습니다.

---

## 3. 새 기능 추가 — `main.py`에 명시 등록

새 기능은 `app/features/<name>/` vertical slice 를 만든 뒤, **`main.py`에 직접 등록**합니다.

### 3.1 등록 단계

```python
# main.py
from app.features import auth, blog, catalog, home, reply, reports, sns, user, <name>  # ← 추가
app.include_router(<name>.router, prefix="/api")                     # ← 취합 한 줄 추가
```

- 라우터: 위 두 줄을 직접 추가합니다(기능 `__init__.py` 가 `router` 공개).
- 모델(메타데이터): **`models_registry`(SSOT)가 `app/features/<name>/models/models.py` 를 자동 수집**하므로 `env.py`·`session.py` 를 손댈 필요가 없습니다. 기능 `__init__.py` 에서 models 를 import 합니다.
- Admin: `app/features/<name>/admin.py` 에 ModelView + `admin_views` 를 만들고,
  `app/features/admin.py` 의 import 와 `ADMIN_VIEWS` 에 한 줄씩 더합니다. 기능 `__init__.py`
  로는 **재노출하지 않습니다** — 재노출하면 라우터만 필요한 import 에도 sqladmin 이 딸려 와
  `ADMIN=false` 가 무의미해집니다.

### 3.2 SQLAdmin 조립 구조

`main.py` 는 `ADMIN=true` 일 때 `register_admin(app, engine)` **하나만** 호출합니다.
그 안에서 두 단계로 나뉩니다.

```text
main.py
  └─ register_admin(app, engine)          외부 진입점 (조립부가 아는 유일한 이름)
       ├─ create_admin_interface(...)     Admin 생성 + /admin 마운트
       └─ register_admin_views(admin)     ADMIN_VIEWS 등록
            └─ ADMIN_VIEWS                등록 대상 SSOT
```

| 함수 | 책임 | 아는 것 |
|---|---|---|
| `create_admin_interface(app, engine)` | `Admin` 생성 → SQLAdmin 이 `/admin` 마운트 | 앱·엔진·제목 (향후 `authentication_backend`) |
| `register_admin_views(admin)` | `ADMIN_VIEWS` 를 선언 순서대로 등록 | 뷰 목록만 — 앱·엔진·설정을 참조하지 않음 |
| `register_admin(app, engine)` | 위 둘을 생성 → 등록 순으로 호출 | 조립 순서 |

> 세 함수는 **SQLAdmin 이나 FastAPI 의 공식 API 가 아니라 이 프로젝트 내부의 조립 함수**입니다.
> 공식 객체는 `Admin` 과 `Admin.add_view()` 뿐이고, 위 함수들은 그 호출 위치를 정리한 것입니다.
>
> 나눈 이유는 두 책임이 서로 다른 것을 알아야 하기 때문입니다 — 생성 쪽은 앱·엔진을,
> 등록 쪽은 뷰 목록만 압니다. 나뉘어 있으면 각각 단독으로 검증할 수 있고, 나중에 인증
> 백엔드를 붙일 자리도 `create_admin_interface()` 하나로 정해집니다(인증 백엔드는 `Admin`
> 생성 인자라 등록 쪽에는 넣을 수 없습니다).
>
> `main.py` 가 두 내부 함수를 직접 부르지 않는 것이 계약입니다. 조립부가 SQLAdmin 의
> 생성·등록 순서를 알 필요가 없습니다. 회귀 가드: `tests/test_admin_wiring.py`.

### 3.3 필수/선택 파일 표

| 파일/디렉토리 | 필수 | 설명 |
|--------------|------|------|
| `__init__.py` | ✅ | `router` 공개 + `models` import |
| `api/routers/router.py` + `v1/` | ✅ | 기능 루트 라우터 + 버전별 엔드포인트 |
| `models/` `schemas/` `services/` `repositories/` `dependencies/` | ✅ | 데이터/로직 계층 |
| `tests/` | ✅ | pytest 테스트 |
| `exceptions.py` | 선택 | 기능 예외 |
| `admin.py` | 선택 | 기능 소유 ModelView + `admin_views` (모델이 있으면 사실상 필수 — `tests/test_admin_wiring.py` 가 강제) |

---

## 4. 요청 처리 & 트랜잭션 경계 (UnitOfWork 미사용)

UnitOfWork 패턴은 사용하지 않습니다. 트랜잭션 경계는 **쓰기 핸들러 본문**이 담당하고,
기능 의존성은 Service 구성만 합니다.

```
Router(view) → Depends(get_<name>_service) → Service(session) → Repository → DB
     ↑ commit() 은 여기서
```

```python
# app/features/<name>/dependencies/<name>_dependencies.py — 구성만 한다
async def get_<name>_service(
    db_session: AsyncSession = Depends(get_writer_db_session),      # 쓰기용
) -> <Name>Service:
    return <Name>Service(db_session)


async def get_<name>_service_readonly(
    db_session: AsyncSession = Depends(get_read_only_db_session),   # 조회용
) -> <Name>Service:
    return <Name>Service(db_session)


# app/features/<name>/api/routers/v1/<name>.py — 커밋은 여기서
async def create_<name>(
    payload: <Name>Create,
    service: <Name>Service = Depends(get_<name>_service),
) -> <Name>Response:
    obj = await service.create(payload)
    await service.commit()          # 트랜잭션 경계 — 응답 생성 전에 끝난다
    return <Name>Response.model_validate(obj)
```

- 뷰(view)는 HTTP 역할과 **커밋 시점 결정**을 맡습니다: 파라미터 수신 → 주입된 Service 호출
  → (쓰기면) `await service.commit()` → 응답 변환.
- 예외로 빠져나가면 `get_writer_db_session` teardown이 `rollback()` 합니다.
- 조회 엔드포인트는 `_readonly` 의존성을 써서 `get_read_only_db_session` 을 받고 커밋하지
  않습니다. `DB_ROUTER_ENABLED` 가 켜지면 replica 로 라우팅되며, 읽기 경로에서 쓰기를
  시도하면 `ReadOnlyRoutingError` 로 즉시 실패합니다 — ORM 구문이든 `text()` 로 쓴 Raw DML
  이든 동일합니다.
- `Service`는 `BaseService`를, Repository 는 데이터 접근 방식에 따라 `BaseRepository`(ORM)
  또는 `RawRepositoryBase`(Raw SQL)를 상속합니다. **둘은 서로 상속하지 않습니다** — §4.1.
- 요청 밖(백그라운드/Celery) 세션은 `background_db_session()` 컨텍스트(별도 풀)를 씁니다.

### 4.1 ORM Repository vs Raw Repository

데이터 접근 방식은 **Repository 계층에서만** 갈립니다. 위 그림에서 달라지는 상자는 하나뿐이고,
Dependency 조립·Service 유스케이스·트랜잭션 경계·Pydantic 응답 검증·OpenAPI 메타데이터는
그대로입니다. 실물 비교는 `app/features/catalog/`(ORM) 와 `app/features/reports/`(Raw) 입니다.

> **단계별 실습**: 이 절이 규칙이라면, 두 방식을 같은 시나리오로 끝까지 만들어 보는 문서는
> [ORM/Raw 워크플로우 개발 지침서](./orm-raw-repository/2026-08-13/workflow-guide.md) 입니다
> (§3 ORM 시나리오 · §4 Raw 시나리오 · §6 Raw SQL 보안 규칙 · §10 코드 리뷰 체크리스트).

| | `BaseRepository` (ORM) | `RawRepositoryBase` (Raw SQL) |
|---|---|---|
| 언제 | 엔티티 생명주기를 다룰 때 (CRUD, 관계 적재) | 집계·리포트·방언 특화 구문 |
| 구문 | SQLAlchemy 표현식 | `sqlalchemy.text()` + **named bind parameter** |
| 반환 | ORM 인스턴스 | `RowMapping` → Service 가 Pydantic DTO 로 검증 |
| 공개 계약 | 최소 CRUD 8개 + 기능별 도메인 메서드 | `fetch_one` / `fetch_all` / `fetch_scalar` / `execute` |

- 두 Base 는 **상속 관계가 없습니다**. Raw 쪽이 ORM Base 를 상속하면 매핑되지 않은 결과에
  ORM 의미(identity map·flush)가 딸려 들어옵니다. 회귀 가드: `scripts/review_gate.py` 의 INV-5.
- Raw 구문에 **문자열 포매팅을 쓰지 않습니다.** 값은 전부 bind parameter 이고, 값으로 바인딩할
  수 없는 자리(컬럼명·정렬 방향)는 `resolve_identifier()` / `resolve_sort_direction()` 로
  **허용 목록에 대조**해서 고릅니다.
- 집계 **결과** 전용 ORM 모델은 만들지 않습니다. 다만 집계의 **원본 테이블**은 이 프로젝트가
  생명주기를 소유하므로 ORM 모델을 둡니다 — `Base.metadata` 에 없으면 Alembic 이 "지워야 할
  테이블" 로 판단합니다(`reports` 의 `SalesOrder`).

> **왜 의존성이 아니라 핸들러인가.** 이전에는 의존성이 `yield` 이후 커밋했습니다. 그런데
> FastAPI 상위 버전에서 yield dependency 의 종료 코드가 **응답 전송 후에** 실행되도록 바뀌면서,
> 커밋이 실패해도 클라이언트는 이미 `201` 을 받은 상태가 됩니다. 커밋을 핸들러 본문으로 옮기면
> 실패가 응답 코드에 정직하게 반영됩니다. 구조 증거: `tests/test_read_path_no_commit.py`.

---

## 4.2 Lifespan 자원 관리 — 기동 준비와 역순 종료

프로세스 수명에 묶인 자원(로그 리스너·DB 엔진·백그라운드 태스크)은 `main.py` 가 아니라
`app/core/resources.py` 의 `manage_application_resources()` 하나가 관리합니다.

```python
# main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with manage_application_resources(app):
        yield
```

- 종료는 **획득의 역순**이며 `AsyncExitStack` 이 순서를 강제합니다:
  백그라운드 태스크 드레인 → DB 엔진 dispose → 로그 리스너 정지.
  순서가 중요합니다 — 태스크가 아직 세션을 쥔 채 엔진을 닫으면 커넥션이 강제로 끊기고,
  로그 리스너를 먼저 내리면 그 과정에서 나는 오류가 어디에도 남지 않습니다.
- 각 단계에 **개별 타임아웃**이 있고 전체에도 상한이 있습니다. 하나가 늦어도 나머지 정리는
  진행됩니다.
- 드레인은 자기 몫의 타임아웃보다 **짧게** 기다립니다(`DRAIN_WAIT_RATIO`). 남는 시간은 취소된
  태스크의 `finally`(세션 rollback·close)가 실제로 실행될 여유입니다 — 같은 값을 주면 취소
  직후 바깥 guard 가 끊어 정리가 실행되지 못합니다.
- 로그는 큐 기반 핸들러를 씁니다. 이벤트 루프가 파일·소켓 I/O 로 막히지 않도록 핸들러는
  큐에 넣기만 하고 별도 스레드가 소비합니다. 큐가 가득 차면 ERROR 이상은 stderr 로 흘리고
  그 아래는 버립니다 — **로깅이 요청 처리를 막지 않는 것**이 우선입니다.

---

## 5. Celery 태스크 — 중앙 집중 include

`app/celery/app.py`는 중앙 태스크 모듈 하나만 `include`합니다(기능별 `worker/` 미사용).

```python
celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
    include=["app.celery.tasks"],
)
```

- 모든 기능 백그라운드 태스크는 `app/celery/tasks.py`에 `@celery_app.task`로 정의합니다.
  (예: `home.aggregate_access_stats`)
- 동기 워커에서 async 코루틴 실행: `app/celery/task.py`의 `run_async(coro)`.
- 태스크 내 DB 세션: `background_db_session()` 컨텍스트.

---

## 6. Alembic 마이그레이션

`migrations/env.py`는 `import_all_models()`(SSOT, `app/core/db/models_registry.py`)로 전 기능 모델을 자동 수집합니다. `app/features/<name>/models/models.py` 가 있으면 자동 등록되므로 새 앱 추가 시 이 파일을 손댈 필요가 없습니다.

```python
from app.core.db.session import Base
from app.core.db.models_registry import import_all_models

import_all_models()          # 디렉터리 스캔으로 전 기능 models 자동 import
target_metadata = Base.metadata
```

**DB URL 우선순위:**
1. `ALEMBIC_DATABASE_URL` 환경 변수 (로컬/CI 오버라이드, SQLite 등)
2. `db_settings.MYSQL_URL` — 비동기 드라이버(`+aiomysql`)를 동기(`+pymysql`)로 치환

```bash
uv run alembic revision --autogenerate -m "add <name> model"
uv run alembic upgrade head
```

---

## 7. 환경 및 툴링

| 명령 | 설명 |
|------|------|
| `uv sync` | 의존성 설치 (가상환경 자동 생성) |
| `uv run uvicorn main:app --reload` | 개발 서버 실행 |
| `uv run alembic upgrade head` | DB 마이그레이션 적용 |
| `uv run pytest` | 테스트 실행 |
| `uv run ruff check .` / `uv run mypy .` | 정적 분석 |
| `docker compose -f compose.test.yaml up -d` | 통합 테스트용 MySQL 8.4 기동(포트 3308) |
| `uv run python scripts/review_gate.py` | 검수 게이트 — 정적분석 + 계층 불변식 + 공개 API 불변 |

> 통합 테스트는 MySQL 이 없으면 **skip** 됩니다(실패가 아닙니다). 스키마 검증만 필요하면
> 컨테이너 없이 `uv run pytest` 로 충분하고, Raw SQL 의 실제 방언 동작까지 확인하려면
> 컨테이너를 띄웁니다. 포트 3308 은 다른 로컬 MySQL 과 겹치지 않도록 고른 값입니다.

`[tool.uv] package = false` — 루트 패키지 빌드 없이 의존성만 설치(flat layout).

---

## 8. 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-06-23 | 기능 모델 레지스트리 아키텍처로 전환, 이 문서 최초 작성 |
| 2026-06-23 | 자동 발견 제거, `app/apps.py` 수동 등록 SSOT로 전환 |
| 2026-07-01 | **표준 FastAPI 배선으로 전환**: `AppRegistry`/`bootstrap.create_app()`/`app/apps.py` 제거, 각 앱 `__init__.py`가 `router` 공개 + `main.py`가 명시 `include_router`로 취합. |
| 2026-08-11 | **`app/features/` 명칭 확정 + SQLAdmin 소유권을 기능으로 이전**: 폴더·import·문서 참조 70개 파일 일괄 정정. 과거 중앙 관리자 패키지 삭제 — ModelView 는 모델과 같은 폴더에 있어야 컬럼 변경이 함께 눈에 들어오고 기능 단위 복사·삭제 시 따라온다. `app/features/<name>/admin.py` 가 ModelView 와 `admin_views` 를 소유하고, 신설 `app/features/admin.py` 가 **명시 import** 로 `ADMIN_VIEWS` 에 취합한다(과거 `getattr(module, "admin_views", [])` 관용 수집은 빈 `admin.py` 를 무신호로 건너뛰어 ADMIN-1 을 낳았으므로 복원하지 않음). 회귀 가드 `tests/test_admin_wiring.py` 에 "모델을 가진 기능은 자기 `admin.py` 를 갖는다" 검사 추가. C-7 자격증명 비노출·생성차단 정책과 공개 API 경로·응답 스키마 불변. |
| 2026-08-11 | **문서 드리프트 정정**: §4 와 README 가 P1-3 이전의 "의존성이 `yield` 후 커밋" 을 계속 설명하고 있었다(코드는 이미 핸들러 커밋). §4 예시를 실제 코드(쓰기/조회 의존성 분리 + 핸들러 `await service.commit()`)로 교체하고, `BaseService` 독스트링도 같이 정정. 아울러 재구조화 잔재 정리 — `tests/features/` 잔류분을 `app/features/<name>/tests/` 로 통합, 이동 중 겹친 디렉터리 레벨과 빈 `tests/scripts/` 제거. |
| 2026-08-11 | **Django 배선 제거 (구조는 vertical slice 유지)**: 옛 중앙 목록 순회 → 명시 `include_router`; 기능별 `admin.py` 관용 수집(`getattr(..., "admin_views", [])`) → 중앙 `app/features/admin.py`의 명시 import(`ADMIN_VIEWS`+`register_admin`); `scripts/new_app.py` 제거. 폴더는 실제 코드 기준 `app/features/` 를 유지한다. 모델 등록은 `models_registry` 디렉터리 스캔 유지. 공개 API 경로·응답 스키마·SQLAdmin 보안 정책 불변. |
| 2026-08-11 | **문서 정합성 재정리**: 삭제된 심화·리팩터링 문서 참조, 존재하지 않는 과거 모듈·관리자 경로 참조, 제거된 중앙 목록 설명을 실제 코드 기준으로 정정. |
| 2026-08-13 | **ORM/Raw Repository 이원화 + 런타임·문서 정비**(§4.1·§4.2 신설). ① lifespan 자원 관리를 `app/core/resources.py` 로 모으고 역순 종료·개별 타임아웃을 강제, 로깅을 큐 기반 비차단 핸들러로 전환. ② 모델 공통 컬럼을 Mixin 으로 정리(스키마 diff 0 을 스냅샷으로 증명). ③ `BaseRepository` 공개 계약을 최소 CRUD 8개로 좁히고(823→185줄) 예외 변환을 전 경로에 통일. ④ `RawRepositoryBase` 신설 — ORM Base 와 상속 관계 없음(INV-5). ⑤ 참조 예제 2종(`catalog`=ORM, `reports`=Raw) + MySQL 8.4 통합 테스트 환경. ⑥ OpenAPI 문서 계약을 규칙 테스트로 고정. 공개 API 경로·응답 스키마는 신규 추가분 외 불변. 결함 17건(CRIT 2·HIGH 5)을 `docs/crp/groups/orm-raw-repository/ledger.md` 에 기록. |
