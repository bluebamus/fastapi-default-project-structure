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
│   ├── domains/                     # 기능 단위 앱 (도메인)
│   │   ├── home/                    # 예시 앱 — 접속 로그
│   │   │   ├── __init__.py          # 하위 라우터를 취합한 router (+ home 은 admin_views) 공개
│   │   │   ├── api/routers/
│   │   │   │   ├── router.py        # 앱 루트 라우터 (<name>_router: v1 취합)
│   │   │   │   └── v1/              # 버전별 엔드포인트 (뷰는 HTTP 역할만)
│   │   │   ├── models/              # SQLAlchemy ORM 모델
│   │   │   ├── schemas/             # Pydantic 요청/응답 스키마
│   │   │   ├── services/            # 비즈니스 로직
│   │   │   ├── repositories/        # 데이터 접근 계층
│   │   │   ├── dependencies/        # FastAPI Depends 헬퍼 (서비스 구성 + 트랜잭션 경계)
│   │   │   ├── admin.py             # SQLAdmin 뷰 (선택; 현재 home 만 구현)
│   │   │   ├── exceptions.py        # 도메인 예외 (선택)
│   │   │   └── tests/               # 도메인 테스트
│   │   └── <name>/                  # 추가 앱은 같은 구조를 따름
│   │
│   ├── core/                        # 프레임워크 인프라 (도메인이 의존)
│   │   ├── exception.py             # 공통 예외 계층 + ErrorResponse
│   │   ├── tags_metadata.py         # OpenAPI 태그 메타데이터
│   │   ├── db/
│   │   │   ├── session.py           # 엔진, 세션 팩토리, 커넥션 풀, background_session
│   │   │   └── redis.py             # Redis 연결 (현재 미구현 스텁)
│   │   ├── models/models_base.py    # SQLAlchemy Base (declarative)
│   │   ├── repositories/
│   │   │   ├── repository_base.py   # BaseRepository
│   │   │   └── crud_base.py         # 제네릭 CRUD 메서드
│   │   ├── services/services_base.py # BaseService
│   │   └── middlewares/
│   │       ├── cors_middleware.py
│   │       ├── user_info_middleware.py
│   │       └── access_log_sink.py
│   │
│   ├── celery/                      # 중앙 Celery (도메인 worker/ 미사용)
│   │   ├── app.py                   # Celery 앱 (include=["app.celery.tasks"])
│   │   ├── tasks.py                 # 중앙 태스크 모듈 (모든 도메인 백그라운드 작업)
│   │   └── task.py                  # run_async() 동기 브릿지
│   │
│   └── utils/                       # 순수 유틸 (외부·상위 계층 의존 없음)
│       ├── logs/                    # 구조화 로깅 (get_logger, setup_uvicorn_logging)
│       ├── authenticator/           # 인증 (JWT·bcrypt)
│       └── pagination/              # 페이지네이션 (순수 dataclass)
│
├── migrations/env.py                # 각 앱 models 모듈을 import 해 Base.metadata 수집
├── scripts/new_app.py               # 앱 스캐폴딩 생성기
└── docs/
    ├── ARCHITECTURE.md              # ← 이 문서 (아키텍처 SSOT)
    ├── concepts/                    # 개념·패턴 심화 해설
    └── refactoring/                 # 변경 기록
```

### 의존 방향

```
domains → core → utils
```

`core`는 `utils`만 알고, `domains`는 `core`를 사용합니다.
`core`는 절대로 `domains`를 import하지 않습니다(도메인이 미들웨어 등에 붙어야 하면
등록 훅으로 연결 — 예: `access_log_sink.register_sink()`).

---

## 2. 표준 FastAPI 배선 (include_router)

자동 스캔(pkgutil/registry)이나 중앙 `app/apps.py` SSOT는 사용하지 않습니다.
각 도메인 앱 패키지의 `__init__.py`가 하위 뷰 라우터를 취합한 `router`를 공개하고,
`main.py`가 이를 명시적으로 import 해 `include_router`로 최종 취합합니다.
이것이 FastAPI 공식(Bigger Applications) 패턴입니다.

### 2.1 앱 패키지 — `router` 공개

```python
# app/domains/<name>/__init__.py
from app.domains.<name>.api.routers.router import <name>_router as router
from app.domains.<name>.models import models as _models  # noqa: F401 (Base.metadata 등록)

__all__ = ["router"]
```

- `api/routers/router.py`의 `<name>_router`가 `api/routers/v1/*`의 서브라우터를 취합합니다.
- home 은 추가로 `admin_views`를 공개하고, import 시 `register_sink()`로 access-log sink를
  미들웨어에 등록합니다(부수효과).

### 2.2 `main.py` — 최종 취합 + 앱 설정

```python
from app.domains import blog, home, reply, sns, user

APPS = [home, blog, reply, sns, user]   # 등록 순서 = 로드 순서

app = FastAPI(...)                        # 인스턴스 + lifespan + ORJSON + 문서 설정
CustomCORSMiddleware(app).configure_cors()
setup_user_info_middleware(app)
_register_exception_handlers(app)         # 4개 글로벌 핸들러
for _app in APPS:
    app.include_router(_app.router, prefix="/api")
_add_health_and_docs(app)                 # /health + Scalar
if app_settings.ADMIN:                    # SQLAdmin (앱별 admin_views 수집)
    ...
```

라우터·미들웨어·예외 핸들러·문서·lifespan·Admin 등록이 전부 `main.py`에서 일어납니다.
별도의 `create_app()` 팩토리나 `bootstrap.py`는 없습니다.

---

## 3. 새 앱 추가 — `main.py`의 `APPS`에 등록

새 앱은 스캐폴딩으로 디렉토리/파일을 생성한 뒤, **`main.py`에 직접 등록**합니다.

### 3.1 스캐폴딩 생성기 (권장)

```bash
uv run python -m scripts.new_app <name>              # 기본 구조
uv run python -m scripts.new_app <name> --with-admin # SQLAdmin 포함
```

생성된 `__init__.py`가 `router`(선택 `admin_views`)를 공개합니다.

### 3.2 등록 단계

```python
# main.py
from app.domains import blog, home, reply, sns, user, <name>   # ← import 추가
APPS = [home, blog, reply, sns, user, <name>]                  # ← 목록에 추가
```

- 라우터/Admin: `APPS` 순회로 자동 취합됩니다(추가 코드 불필요).
- 모델(메타데이터): 앱 `__init__.py`의 `models` import(주석 해제)로 `Base.metadata`에 등록.
- Alembic: `migrations/env.py`의 import 목록에도 새 앱 models 모듈을 추가합니다.

### 3.3 필수/선택 파일 표

| 파일/디렉토리 | 필수 | 설명 |
|--------------|------|------|
| `__init__.py` | ✅ | `router`(선택 `admin_views`) 공개 |
| `api/routers/router.py` + `v1/` | ✅ | 앱 루트 라우터 + 버전별 엔드포인트 |
| `models/` `schemas/` `services/` `repositories/` `dependencies/` | ✅ | 데이터/로직 계층 |
| `tests/` | ✅ | pytest 테스트 |
| `admin.py` | 선택 | SQLAdmin 뷰 (`--with-admin`) |
| `exceptions.py` | 선택 | 도메인 예외 |

---

## 4. 요청 처리 & 트랜잭션 경계 (UnitOfWork 미사용)

UnitOfWork 패턴은 사용하지 않습니다. 트랜잭션 경계는 **기능 의존성**이 담당합니다.

```
Router(view) → Depends(get_<name>_service) → Service(session) → Repository → DB
```

```python
# app/domains/<name>/dependencies/<name>_dependencies.py
async def get_<name>_service(
    session: AsyncSession = Depends(get_session),
) -> AsyncGenerator[<Name>Service, None]:
    service = <Name>Service(session)
    yield service
    await session.commit()          # 요청 성공 시 커밋 = 트랜잭션 경계
```

- 뷰(view)는 HTTP 역할만 합니다: 파라미터 수신 → 주입된 Service 호출 → 응답 변환.
- 성공 시 의존성이 `commit()`, 예외 시 `get_session` teardown이 `rollback()`.
- `Service`는 `BaseService`를, `Repository`는 `BaseRepository`(제네릭 CRUD)를 상속합니다.
- 요청 밖(백그라운드/Celery) 세션은 `background_session()` 컨텍스트(별도 풀)를 씁니다.

---

## 5. Celery 태스크 — 중앙 집중 include

`app/celery/app.py`는 중앙 태스크 모듈 하나만 `include`합니다(도메인 `worker/` 미사용).

```python
celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
    include=["app.celery.tasks"],
)
```

- 모든 도메인 백그라운드 태스크는 `app/celery/tasks.py`에 `@celery_app.task`로 정의합니다.
  (예: `home.aggregate_access_stats`)
- 동기 워커에서 async 코루틴 실행: `app/celery/task.py`의 `run_async(coro)`.
- 태스크 내 DB 세션: `background_session()` 컨텍스트.

---

## 6. Alembic 마이그레이션

`migrations/env.py`는 각 도메인 앱의 `models` 모듈을 명시적으로 import 해 메타데이터를 수집합니다.

```python
from app.core.db.session import Base
import app.domains.blog.models.models   # noqa
import app.domains.home.models.models   # noqa
# ... 새 앱 추가 시 여기에 한 줄 추가
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
| `uv run python -m scripts.new_app <name>` | 새 앱 스캐폴딩 생성 |
| `uv run alembic upgrade head` | DB 마이그레이션 적용 |
| `uv run pytest` | 테스트 실행 |
| `uv run ruff check .` / `uv run mypy .` | 정적 분석 |

`[tool.uv] package = false` — 루트 패키지 빌드 없이 의존성만 설치(flat layout).

---

## 8. 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-06-23 | 도메인 레지스트리 아키텍처로 전환, 이 문서 최초 작성 |
| 2026-06-23 | 자동 발견 제거, `app/apps.py` 수동 등록 SSOT로 전환 |
| 2026-07-01 | **표준 FastAPI 배선으로 전환**: `AppRegistry`/`bootstrap.create_app()`/`app/apps.py` 제거, 각 앱 `__init__.py`가 `router` 공개 + `main.py`의 `APPS`가 `include_router`로 취합. 이 문서를 현행 코드에 맞춰 전면 갱신(UnitOfWork 서술 제거 — 코드에서 이미 제거되어 의존성이 트랜잭션 경계 담당; Celery 중앙 `app/celery/tasks.py` include; Alembic 명시 import). |
