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
│   ├── domains/                     # 기능 단위 앱 (도메인)
│   │   ├── home/                    # 예시 앱 — 접속 로그
│   │   │   ├── config.py            # AppConfig 서브클래스 (레지스트리 진입점)
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
│   │   ├── registry.py              # AppConfig / AppRegistry
│   │   ├── bootstrap.py             # create_app() 팩토리
│   │   ├── exception.py             # 공통 예외 계층
│   │   ├── tags_metadata.py         # OpenAPI 태그 메타데이터
│   │   ├── db/
│   │   │   ├── session.py           # 엔진, 세션 팩토리, 커넥션 풀
│   │   │   ├── unit_of_work.py      # BaseUnitOfWork (세션·트랜잭션만)
│   │   │   └── redis.py             # Redis 연결
│   │   ├── celery/
│   │   │   ├── app.py               # Celery 앱 (autodiscover)
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
│   └── env.py                       # AppRegistry로 메타데이터 자동 수집
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

## 2. 자동 발견(Auto-Discovery) 아키텍처

### 2.1 AppConfig 계약

각 앱은 `config.py`에 `AppConfig`를 상속한 클래스 **하나**를 선언합니다.

```python
# app/domains/<name>/config.py
from fastapi import APIRouter
from app.core.registry import AppConfig


class <Name>Config(AppConfig):
    name = "<name>"          # 고유 앱 이름 (중복 시 RuntimeError)
    category = "domain"      # 분류 레이블 (자유 텍스트)
    prefix = "/api"          # 라우터 마운트 접두사
    enabled = True           # False면 레지스트리가 무시
    order = 100              # 로드 순서 (낮을수록 먼저, 앱 간 의존 제어)

    def router(self) -> APIRouter:
        from app.domains.<name>.api.routers.router import <name>_router
        return <name>_router

    def admin_views(self) -> list[type]:   # 선택: SQLAdmin 뷰
        return []

    def beat_schedule(self) -> dict:       # 선택: Celery Beat 스케줄 조각
        return {}
```

`AppConfig.package` 프로퍼티는 자동으로 `app.domains.<name>`을 반환합니다.

### 2.2 AppRegistry 동작

`AppRegistry.discover(package="app.domains")`는 `pkgutil.walk_packages`로
`app/domains` 하위를 재귀 스캔하여 `*.config` 모듈만 import합니다.
각 모듈에서 `AppConfig`의 직접/간접 서브클래스를 수집하고,
`enabled=True`인 것만 `(order, name)` 순으로 정렬합니다.

```
create_app() 호출
    └─ registry.discover()        → app/domains 재귀 스캔, AppConfig 수집
    └─ registry.import_models()   → Base.metadata 채움 (Alembic/create_db_tables 공용)
    └─ registry.install_routers() → 각 앱의 router() 결과를 FastAPI에 마운트
    └─ registry.install_admin()   → admin_views() 결과를 SQLAdmin에 등록
```

### 2.3 main.py는 단 5줄

```python
"""FastAPI 진입점. 모든 조립은 create_app() 안에서 레지스트리가 수행한다."""
from app.core.bootstrap import create_app
from config import app_settings

app = create_app()
```

---

## 3. 새 앱 추가 — 중앙 파일 수정 없음

새 앱 추가 시 **main.py, migrations/env.py, celery/app.py 등 어떤 중앙 파일도 수정할 필요가 없습니다.**
레지스트리가 부팅 시 자동으로 발견합니다.

### 3.1 스캐폴딩 생성기 사용 (권장)

```bash
# 기본 (config + router + unit_of_work만 생성)
uv run python -m scripts.new_app <name>

# 카테고리 지정 + Celery 워커 + SQLAdmin 포함
uv run python -m scripts.new_app <name> --category domain --with-worker --with-admin
```

생성 결과: `app/domains/<name>/` 아래 필수 디렉토리와 파일이 즉시 생성됩니다.

### 3.2 수동 추가 단계 (참고)

| 단계 | 작업 |
|------|------|
| 1 | `app/domains/<name>/config.py` — `AppConfig` 서브클래스 선언 |
| 2 | `app/domains/<name>/models/` — SQLAlchemy 모델 정의 |
| 3 | `app/domains/<name>/schemas/` — Pydantic 스키마 |
| 4 | `app/domains/<name>/repositories/` — BaseRepository 확장 |
| 5 | `app/domains/<name>/unit_of_work/` — BaseUnitOfWork 확장 |
| 6 | `app/domains/<name>/services/` — 비즈니스 로직 |
| 7 | `app/domains/<name>/api/routers/router.py` + `v1/` — 엔드포인트 |

config.py의 `router()` 훅만 올바르게 반환하면 서버 재시작 시 자동 등록됩니다.

### 3.3 필수/선택 파일 표

| 파일/디렉토리 | 필수 | 설명 |
|--------------|------|------|
| `config.py` | ✅ | AppConfig 서브클래스 — 레지스트리 진입점 |
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

## 4. Celery 자동 발견

`app/core/celery/app.py`는 AppRegistry를 사용해 모든 앱의 태스크를 자동 등록합니다.

```python
registry = AppRegistry()
registry.discover()
celery_app.autodiscover_tasks(
    registry.celery_packages(),        # ["app.domains.home", "app.domains.user", ...]
    related_name="worker.tasks"        # 각 패키지의 worker/tasks.py를 탐색
)
```

- 앱별 태스크: `app/domains/<name>/worker/tasks.py`
- Celery Beat 스케줄: `AppConfig.beat_schedule()` 훅 구현 → 레지스트리가 병합
- 동기 워커에서 async 코루틴 실행: `app/core/celery/task.py`의 `run_async(coro)`

---

## 5. Alembic 마이그레이션

`migrations/env.py`는 중앙 모델 import 목록 없이 메타데이터를 수집합니다.

```python
from app.core.db.session import Base
from app.core.registry import AppRegistry

_reg = AppRegistry()
_reg.discover()
_reg.import_models()          # 각 앱의 models/ 패키지를 import → Base.metadata 채움

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
