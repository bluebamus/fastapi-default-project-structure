# 개발 가이드

구조 설명은 [ARCHITECTURE](./ARCHITECTURE.md), 실행·설정은 [README](../README.md) 를 봅니다.

## 1. 새 기능 추가

생성 스크립트는 없습니다. 가장 가까운 기존 기능을 복사해 이름을 바꾸는 것이 빠릅니다 — 게시판형 CRUD 는
`blog`, ORM 참조 예제는 `catalog`, Raw SQL 은 `reports`.

1. **모델** `app/features/<name>/models/models.py` — `app/core/models/models_base.py` 의 Mixin 을 조합합니다
   (변경 가능한 엔티티는 `UUIDTimestampModel`, 생성 후 불변이면 `UUIDCreatedModel`). 시각 컬럼은 `UTCDateTime`.
   `models/models.py` 가 있으면 `app/core/db/models_registry.py` 가 디렉터리에서 찾아 `Base.metadata` 에
   등록하므로 등록 목록을 고칠 곳은 없습니다.
2. **스키마** `schemas/<name>_schema.py` — 생성·수정·응답 DTO. PATCH 용 DTO 는 `app/core/schemas.py` 의 `PatchSchema` 를
   상속해, nullable 이 아닌 필드에 명시적 `null` 이 오면 422 로 막습니다.
3. **Repository** `repositories/` — ORM 은 `BaseRepository[Model]`, Raw SQL 은 `RawRepositoryBase`. Base 의
   공개 API 로 안 되는 쿼리만 명시적 메서드로 추가하고 `self.execute(...)` 로 실행합니다(DB 오류 변환을 거치게).
   커밋하지 않습니다.
4. **Service** `services/` — `BaseService` 를 상속해 세션으로 Repository 를 만듭니다. 수정·삭제 권한은
   주입받은 `OwnershipPolicy` 로 판정합니다. 커밋하지 않습니다.
5. **Dependency** `dependencies/` — 쓰기용은 `get_writer_db_session`, 조회용은 `get_read_only_db_session` 으로
   세션을 받아 Service 를 조립하는 provider 를 따로 둡니다. 협력 객체는 `app/core/security/dependencies.py`
   의 provider 로 받습니다(다른 기능을 import 하지 않습니다).
6. **View** `api/routers/v1/<name>.py` — 모든 path operation 은 `async def` 이고 접근 수준을 정확히 하나
   선언합니다(`dependencies=[Public]` 등, 또는 `principal: CurrentPrincipal` 인자). 쓰기 핸들러는 응답 DTO 를
   검증한 뒤 `await service.commit()` 을 한 번 부르고 반환합니다. `api/routers/router.py` 에서
   `prefix="/v1/<name>"`, `tags=["<Name>"]` 로 묶습니다.
7. **패키지** `__init__.py` — `router` 를 공개하고 `models` 를 import 합니다(`blog/__init__.py` 와 같은 형태).
8. **배선** `main.py` — `app.include_router(<name>.router, prefix="/api")` 한 줄을 `AccessPolicyGuard().verify(app)`
   **위에** 추가합니다. 태그 설명은 `app/core/tags_metadata.py` 에 더합니다.
9. **관리 화면**(선택) — `admin.py` 에 `ModelView` 와 `admin_views` 를 만들고 `app/features/admin.py` 의 import 와
   `ADMIN_VIEWS` 에 한 줄씩 더합니다. 패키지 `__init__.py` 로 재노출하지 않습니다(`ADMIN_DISABLED=true` 에서
   sqladmin 이 import 되지 않게).
10. **Celery**(선택) — `tasks.py` 에 태스크를 두면 worker 가 자동으로 include 합니다. async 코드는
    `app.celery.task.run_async` 로, 세션은 `background_db_session()` 으로 열고 쓰기면 태스크가 커밋합니다.
    주기 실행은 그 모듈에서 `celery_app.conf.beat_schedule` 에 등록합니다(`home/tasks.py` 참고).
11. **마이그레이션** — 아래 3절.
12. **테스트** `app/features/<name>/tests/` — 아래 2절.

로그는 `get_logger(__name__)` 또는 클래스에서 `LoggerMixin` 의 `self.log` 를 씁니다. 새 비밀 설정(이름이
`*_USER`·`*_PASSWORD`·`*_KEY` 이거나 `SECRET` 을 담는 것)을 추가하면 `config.LOG_SECRET_SETTINGS` 에도 넣습니다
— 로그 마스킹 대상이 되고, 빠지면 테스트가 실패합니다.

## 2. 테스트

```bash
uv run python -m pytest                       # 전체
uv run python -m pytest app/features/blog     # 기능 하나
uv run python -m pytest --cov=app --cov-branch --cov-report=term-missing
```

- `pyproject.toml` 이 `DEBUG=true`, `ENV=test` 를 줍니다 — 설정 검사가 꺼지고 `.env` 없이 돕니다.
  `asyncio_mode = "auto"` 라 `async def test_*` 에 마커가 필요 없습니다. 폐기 예고(`DeprecationWarning`)는
  실패로 취급합니다.
- **외부 자원을 쓰지 않습니다.** DB 는 `sqlite+aiosqlite:///:memory:`(`StaticPool`) 에 `Base.metadata.create_all`,
  Redis 는 `fakeredis.FakeAsyncRedis` 를 `get_redis` 의존성에 끼웁니다. 테스트는 lifespan 을 돌리지 않습니다
  (`httpx.ASGITransport`).
- skip·xfail 을 남기지 않습니다 — CI 가 요약에서 찾아 실패시킵니다.

위치:

| 위치 | 대상 |
|---|---|
| `app/features/<name>/tests/` | 그 기능의 API(상태 코드·검증·응답·권한·소유권)와 트랜잭션 경계 |
| `tests/core/` | `app/core`·`app/celery` 모듈 — 세션·라우터·Repository Base·보안 부품·자원 수명주기·미들웨어·Celery |
| `tests/utils/` | 로깅·페이지네이션 |
| `tests/scripts/` | `scripts/` 의 동작 |
| `tests/` (최상위) | 여러 기능을 가로지르는 앱 수준 동작 — 관리 화면, 인가, 예외 응답, 헬스체크, OpenAPI, 라우터·모델 등록, 트랜잭션 배선 |

공용 헬퍼:

- `tests/session_overrides.py` 의 `override_db_sessions(app, maker)` — 두 세션 의존성을 테스트 세션으로 바꾸되
  운영과 같은 읽기 전용/쓰기 표시를 붙입니다. GET 이 몰래 쓰면 테스트에서도 `ReadOnlyRoutingError` 로 실패합니다.
  엔드포인트 테스트는 세션 의존성을 직접 override 하지 않고 이 함수를 씁니다.
- `tests/auth_headers.py` 의 `bearer(principal)` — 실제 `TokenService` 로 발급한 access 토큰 헤더.
  `SUPERUSER`·`ALICE`·`BOB` 주체가 있습니다.
- `tests/admin_csrf.py` — 관리 화면 로그인·CSRF 토큰을 다루는 헬퍼.

작성 규칙:

- 사용자가 관찰하는 동작(상태 코드·응답 본문·저장 결과·헤더·로그)을 검사합니다. 내부 구현의 이름이나 파일
  위치를 고정하는 테스트는 만들지 않습니다.
- 인증·권한이 있는 엔드포인트는 401(토큰 없음)·403(권한 없음)·소유권(남의 리소스) 경우를 함께 둡니다.
- 쓰기 경로는 커밋 횟수·실패 시 롤백을, 조회 경로는 커밋하지 않음을 확인합니다.
- 커버리지 하한은 `pyproject.toml` 의 `[tool.coverage.report] fail_under` 하나가 정합니다(명령줄에
  `--cov-fail-under` 를 두지 않습니다).

## 3. 마이그레이션 (Alembic)

`migrations/env.py` 가 `models_registry.import_all_models()` 로 모든 모델을 등록하고, 접속 URL 은
`db_settings.ALEMBIC_URL` 에서 받습니다 — `ALEMBIC_DATABASE_URL` 이 있으면 그것, 없으면 primary MySQL DSN 을
동기 드라이버(pymysql)로 바꾼 값입니다.

```bash
uv run alembic revision --autogenerate -m "add <name>"   # 모델 변경 후
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic heads                                     # head 는 하나여야 한다 (CI 가 검사)
```

- 리비전 히스토리는 현재 스키마 전체를 만드는 baseline 하나(`migrations/versions/8b12244e9bcf_baseline_schema.py`)
  에서 시작합니다.
- autogenerate 는 `UTCDateTime` 을 앱 import 없는 `sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")`
  로 렌더하고, MySQL 에서 소수 초 자릿수가 다르면 드리프트로 잡습니다(`app/core/models/types.py` 의
  `render_item`·`compare_type`). 생성된 리비전은 읽어 보고 커밋합니다.
- `tests/core/test_migrations.py` 가 빈 SQLite 에 `upgrade head` 후 모델과 차이가 없는지, `downgrade base` 후
  테이블이 남지 않는지 확인합니다 — 모델만 바꾸고 리비전을 빠뜨리면 이 테스트가 실패합니다.
- `DEBUG=true` 의 기동 시 테이블 생성은 없는 테이블만 만드는 개발 편의 기능이고 컬럼 변경을 반영하지 않습니다.

## 4. 게이트와 CI

`scripts/review_gate.py`:

| 검사 | 내용 |
|---|---|
| pytest | 전건 통과, 요약에 `skipped`·`xfailed`·`xpassed`·`deselected` 가 있어도 실패 (`--fast` 면 생략) |
| ruff check · ruff format --check · mypy | 정적 분석 |
| pip-audit | 설치된 의존성에 공개된 취약점 권고 0건 |
| 계층 | View 가 `execute()`·`AsyncSession` 을 직접 쓰지 않음, Repository·Dependency 가 `commit()` 하지 않음, Raw Base 가 ORM Base 를 상속하지 않음 |
| 공개 API 불변 | `tests/openapi_baseline.json` 의 operation 이 경로·메서드·2xx 상태 코드까지 그대로 (추가는 허용) |
| 테이블 삭제 없음 | `app/`·`main.py` 에 `drop_all` 이 없음 |
| 빈 .py 없음 | `__init__.py` 를 뺀 내용 없는 파일 |
| async path operation | 모든 path operation 이 `async def` 이고 `open()`·`time.sleep()` 같은 동기 I/O 가 없음 |
| 종료 테스트 수집 | 취소·신호 종료 테스트가 지워지거나 이름이 바뀌지 않음 |

공개 API 를 의도적으로 바꾸거나 지웠다면 `tests/openapi_baseline.json` 을 새 스펙으로 갱신합니다
— 현재 `main.app.openapi()` 를 그대로 저장합니다:

```bash
ENV=test uv run python -c "import json, pathlib, main; pathlib.Path('tests/openapi_baseline.json').write_text(json.dumps(main.app.openapi(), ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')"
```

CI(`.github/workflows/ci.yml`, job `gate`): `uv sync --locked` → ruff → mypy(콜드 캐시) → bandit(MEDIUM 이상,
`app`·`main.py`·`config.py`) → `review_gate --fast` → `pytest -rsxX --cov` → skip·xfail 0건 확인 →
`alembic heads` 단일 head. push·PR 과 매주 월요일 09:00(KST)에 돕니다. 배포·이미지 빌드는 이 저장소 범위
밖입니다.
