# 아키텍처 문서

> 설계 배경과 의사결정 근거는 [`docs/proposer/index.html`](proposer/index.html)을 참고하세요.

이 문서는 프로젝트의 유일한 공식 아키텍처 소스입니다.
코드와 문서 간 불일치가 있으면 코드가 정답이며, 이 문서를 업데이트하세요.

---

## 1. 폴더 분류체계

```
fastapi-default-project-structure/
├── main.py                          # 진입점: app = create_app() 한 줄
├── config.py                        # Pydantic Settings (app/db/redis/timezone)
├── pyproject.toml                   # 의존성 + [tool.uv] package = false
│
├── app/
│   ├── apps.py                      # 앱 수동 등록 SSOT (routers/register_models/admin_views/CELERY_TASK_MODULES)
│   ├── domains/                     # 기능 단위 앱 (도메인)
│   │   ├── home/                    # 예시 앱 — 접속 로그
│   │   │   ├── api/
│   │   │   │   └── routers/
│   │   │   │       ├── router.py    # 앱 루트 라우터 집합
│   │   │   │       └── v1/          # 버전별 엔드포인트
│   │   │   ├── models/              # SQLAlchemy ORM 모델
│   │   │   ├── schemas/             # Pydantic 요청/응답 스키마
│   │   │   ├── services/            # 비즈니스 로직
│   │   │   ├── repositories/        # 데이터 접근 계층
│   │   │   ├── unit_of_work/        # 도메인 전용 UnitOfWork 패키지
│   │   │   ├── worker/              # Celery 태스크 (선택)
│   │   │   ├── admin.py             # SQLAdmin 뷰 (선택)
│   │   │   ├── dependencies.py      # FastAPI 의존성 (선택)
│   │   │   ├── exceptions.py        # 도메인 예외 (선택)
│   │   │   └── tests/               # 도메인 테스트
│   │   └── <name>/                  # 추가 앱은 같은 구조를 따름
│   │
│   ├── core/                        # 프레임워크 인프라 (도메인이 의존)
│   │   ├── bootstrap.py             # create_app() 팩토리
│   │   ├── exception.py             # 공통 예외 계층
│   │   ├── tags_metadata.py         # OpenAPI 태그 메타데이터
│   │   ├── db/
│   │   │   ├── session.py           # 엔진, 세션 팩토리, 커넥션 풀
│   │   │   ├── unit_of_work.py      # BaseUnitOfWork (세션·트랜잭션만)
│   │   │   └── redis.py             # Redis 연결
│   │   ├── celery/
│   │   │   ├── app.py               # Celery 앱 (app/apps.py의 CELERY_TASK_MODULES 명시 include)
│   │   │   └── task.py              # run_async() 동기 브릿지
│   │   ├── models/
│   │   │   └── models_base.py       # SQLAlchemy Base (declarative)
│   │   ├── repositories/
│   │   │   ├── repository_base.py   # BaseRepository
│   │   │   └── crud_base.py         # 제네릭 CRUD 메서드
│   │   ├── services/
│   │   │   └── services_base.py     # BaseService
│   │   └── middlewares/
│   │       ├── cors_middleware.py
│   │       ├── user_info_middleware.py
│   │       └── access_log_sink.py
│   │
│   └── shared/                      # 순수 유틸리티 (외부 의존 없음)
│       ├── logging/                 # 구조화 로깅 (get_logger, setup_uvicorn_logging)
│       └── pagination/              # 페이지네이션 헬퍼
│
├── migrations/                      # Alembic 마이그레이션
│   └── env.py                       # app/apps.py의 register_models()로 메타데이터 수집
├── scripts/
│   └── new_app.py                   # 앱 스캐폴딩 생성기
└── docs/
    ├── ARCHITECTURE.md              # ← 이 문서
    └── proposer/index.html          # 설계 결정 근거 (HTML)
```

### 의존 방향

```
domains → core → shared
```

`core`는 `shared`만 알고, `domains`는 `core`를 사용합니다.
`core`는 절대로 `domains`를 import하지 않습니다.

---

## 2. 수동 등록(Manual Registration) 아키텍처

자동 스캔(pkgutil/inspect/동적 importlib)은 사용하지 않습니다. 모든 앱은
`app/apps.py` 단일 진실 공급원(SSOT)에 **명시적으로** 등록합니다.
이 방식은 동작이 예측 가능하고, 등록 내용이 한 파일에 모여 추적이 쉽습니다.

### 2.1 SSOT — `app/apps.py`

```python
# app/apps.py
from dataclasses import dataclass
from fastapi import APIRouter
import importlib


@dataclass(frozen=True)
class RouterSpec:
    router: APIRouter
    prefix: str = "/api"


def routers() -> list[RouterSpec]:
    # home_router 반환 전, access-log sink를 명시 등록(부수효과)
    from app.domains.home.access_log_sink import register_sink
    register_sink()
    from app.domains.home.api.routers.router import home_router
    return [RouterSpec(router=home_router, prefix="/api")]


_MODEL_MODULES = ["app.domains.home.models.models"]


def register_models() -> None:
    for module_path in _MODEL_MODULES:
        importlib.import_module(module_path)


def admin_views() -> list[type]:
    from app.domains.home.admin import UserAccessLogAdmin
    return [UserAccessLogAdmin]


CELERY_TASK_MODULES = ["app.domains.home.worker.tasks"]
BEAT_SCHEDULE: dict = {}
```

- 라우터/Admin/모델은 **지연 import**하여 모듈 로드 시 순환참조·부수효과를 피합니다.
- `routers()`는 home 라우터를 반환하기 전에 `register_sink()`를 호출해
  access-log sink를 미들웨어에 등록합니다(이전 `home/config.py`의 부수효과 대체).

### 2.2 create_app() 소비 흐름

```
create_app() 호출
    └─ register_models()                         → Base.metadata 채움 (Alembic/create_db_tables 공용)
    └─ for spec in routers(): include_router(...) → 각 RouterSpec을 FastAPI에 마운트
    └─ for v in admin_views(): admin.add_view(v)  → SQLAdmin에 뷰 등록
```

### 2.3 main.py의 핵심은 `app = create_app()` 한 줄

```python
"""FastAPI 진입점. 모든 조립은 create_app() 안에서 수행한다(app/apps.py 등록 기반)."""
from app.core.bootstrap import create_app
from config import app_settings

app = create_app()

if __name__ == "__main__":
    import uvicorn
    from app.shared.logging import setup_uvicorn_logging

    uvicorn.run(
        "main:app", host="0.0.0.0", port=8000,
        reload=app_settings.DEBUG, log_config=setup_uvicorn_logging(),
    )
```

라우터·예외 핸들러·미들웨어·Admin 등록은 전부 `create_app()` 안에서 일어나며,
앱 등록 항목은 `app/apps.py`에서 가져옵니다.

---

## 3. 새 앱 추가 — `app/apps.py`에 수동 등록

새 앱은 스캐폴딩으로 디렉토리/파일을 생성한 뒤, **`app/apps.py`에 직접 등록**해야 합니다.
자동 발견이 없으므로 등록을 빠뜨리면 라우터/모델/Admin/태스크가 연결되지 않습니다.

### 3.1 스캐폴딩 생성기 사용 (권장)

```bash
# 기본 (router + unit_of_work 생성)
uv run python -m scripts.new_app <name>

# Celery 워커 + SQLAdmin 포함
uv run python -m scripts.new_app <name> --with-worker --with-admin
```

생성 결과: `app/domains/<name>/` 아래 필수 디렉토리와 파일이 즉시 생성됩니다.
실행 후 출력되는 안내에 따라 `app/apps.py`에 등록 항목을 추가합니다.

### 3.2 `app/apps.py` 등록 단계

| 대상 | 수정 위치 |
|------|----------|
| 라우터 | `routers()` 반환 리스트에 `RouterSpec(router=<name>_router)` 추가 |
| 모델 | `_MODEL_MODULES`에 `"app.domains.<name>.models.models"` 추가 |
| Admin 뷰 (선택) | `admin_views()` 반환 리스트에 ModelView 클래스 추가 |
| Celery 태스크 모듈 (선택) | `CELERY_TASK_MODULES`에 `"app.domains.<name>.worker.tasks"` 추가 |
| Beat 스케줄 (선택) | `BEAT_SCHEDULE`에 스케줄 항목 추가 |

### 3.3 필수/선택 파일 표

| 파일/디렉토리 | 필수 | 설명 |
|--------------|------|------|
| `api/routers/router.py` | ✅ | 앱 루트 라우터 |
| `api/routers/v1/` | ✅ | 버전별 엔드포인트 디렉토리 |
| `models/` | ✅ | SQLAlchemy ORM 모델 |
| `schemas/` | ✅ | Pydantic 요청/응답 스키마 |
| `services/` | ✅ | 비즈니스 로직 |
| `repositories/` | ✅ | 데이터 접근 계층 |
| `unit_of_work.py` 또는 `unit_of_work/` | ✅ | 도메인 전용 UnitOfWork |
| `tests/` | ✅ | pytest 테스트 |
| `worker/tasks.py` | 선택 | Celery 태스크 (`--with-worker`) |
| `admin.py` | 선택 | SQLAdmin 뷰 (`--with-admin`) |
| `dependencies.py` | 선택 | FastAPI Depends 헬퍼 |
| `exceptions.py` | 선택 | 도메인 예외 |

---

## 4. Celery 태스크 등록 — 명시적 include (autodiscover 미사용)

`app/core/celery/app.py`는 `app/apps.py`의 `CELERY_TASK_MODULES` 목록을 그대로
Celery 생성자의 `include=`에 전달합니다. 자동 스캔(`autodiscover_tasks`)은
사용하지 않으며, 태스크 모듈은 모델 등록(`_MODEL_MODULES`)과 대칭으로 명시합니다.

```python
from app.apps import BEAT_SCHEDULE, CELERY_TASK_MODULES

celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
    include=CELERY_TASK_MODULES,       # ["app.domains.home.worker.tasks", ...]
)
```

- 워커 부팅 시 Celery가 `include` 모듈을 import하여 `@celery_app.task` 데코레이터가
  태스크를 등록합니다(autodiscover와 동일한 시점·결과, 단 스캔 마법 없음).
- 앱별 태스크: `app/domains/<name>/worker/tasks.py`
- 새 앱의 태스크 모듈은 `app/apps.py`의 `CELERY_TASK_MODULES`에 직접 추가합니다.
- Celery Beat 스케줄: `app/apps.py`의 `BEAT_SCHEDULE`에 항목 추가
- 동기 워커에서 async 코루틴 실행: `app/core/celery/task.py`의 `run_async(coro)`

---

## 5. Alembic 마이그레이션

`migrations/env.py`는 `app/apps.py`의 `register_models()`로 메타데이터를 수집합니다.

```python
from app.core.db.session import Base
from app.apps import register_models

register_models()             # _MODEL_MODULES를 import → Base.metadata 채움

target_metadata = Base.metadata
```

**DB URL 우선순위:**
1. `ALEMBIC_DATABASE_URL` 환경 변수 (로컬/CI 오버라이드, SQLite 등)
2. `db_settings.MYSQL_URL` — 비동기 드라이버(`+aiomysql`)를 동기(`+pymysql`)로 치환

```bash
# 마이그레이션 생성
uv run alembic revision --autogenerate -m "add <name> model"

# 마이그레이션 적용
uv run alembic upgrade head
```

---

## 6. UnitOfWork 패턴

### 6.1 선언형 방식 (권장)

```python
# app/domains/<name>/unit_of_work/<name>_unit_of_work.py
from app.core.db.unit_of_work import BaseUnitOfWork
from app.domains.<name>.repositories.<name>_repository import <Name>Repository


class <Name>UnitOfWork(BaseUnitOfWork):
    items: <Name>Repository
    repositories = {"items": <Name>Repository}   # __aenter__ 시 자동 초기화
```

`repositories` 맵을 선언하면 `BaseUnitOfWork.__aenter__`가 자동으로 인스턴스화합니다.

### 6.2 사용 방법

```python
# 일반 요청 (FastAPI 세션 주입)
async with <Name>UnitOfWork(session) as uow:
    result = await uow.items.get_by_id(item_id)
    await uow.commit()

# 백그라운드 태스크 (별도 커넥션 풀)
async with <Name>UnitOfWork(background=True) as uow:
    await uow.items.create({...})
    await uow.commit()
```

`background=True`는 `BackgroundSessionLocal`(별도 풀)을 사용하여
메인 API 풀 고갈을 방지합니다.

### 6.3 의존 방향

```
domains/<name>/unit_of_work/  →  core/db/unit_of_work.py  →  core/db/session.py
```

`core`는 절대로 `domains`를 import하지 않습니다.

---

## 7. 환경 및 툴링

| 명령 | 설명 |
|------|------|
| `uv sync` | 의존성 설치 (가상환경 자동 생성) |
| `uv run uvicorn main:app --reload` | 개발 서버 실행 |
| `uv run python -m scripts.new_app <name>` | 새 앱 스캐폴딩 생성 |
| `uv run alembic upgrade head` | DB 마이그레이션 적용 |
| `uv run pytest` | 테스트 실행 |
| `uv add <pkg>` | 런타임 의존성 추가 |
| `uv add --dev <pkg>` | 개발 의존성 추가 (`[dependency-groups]`) |

`pyproject.toml`의 `[tool.uv] package = false` 설정으로 루트 패키지 빌드 없이
의존성만 설치합니다(flat layout 애플리케이션).

---

## 8. 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-06-23 | 도메인 레지스트리 아키텍처로 전환, 이 문서 최초 작성 |
| 2026-06-23 | 자동 발견(AppRegistry/AppConfig) 제거, `app/apps.py` 수동 등록 SSOT로 전환 |
| 2026-06-23 | Celery `autodiscover_tasks` 제거, `CELERY_TASK_MODULES` 명시 `include`로 전환 |
