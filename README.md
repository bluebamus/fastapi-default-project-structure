# FastAPI Default Project Structure

Repository 패턴과 계층 분리를 적용한 FastAPI 백엔드 템플릿입니다.
각 기능 패키지(`app/features/<name>/`)가 자기 `router` 를 공개하고, `main.py` 가 명시적
`include_router` 로 취합합니다 — 자동 탐색이나 중앙 레지스트리는 없습니다.

## 목차

- [문서 안내](#문서-안내)
- [특징](#특징)
- [기술 스택](#기술-스택)
- [빠른 시작](#빠른-시작)
- [환경 변수](#환경-변수)
- [테스트·검수·CI](#테스트검수ci)
- [API](#api)
- [운영 배포 체크리스트](#운영-배포-체크리스트)

---

## 문서 안내

이 표가 저장소 문서의 유일한 색인입니다. 코드와 문서가 다르면 코드가 정답이고, 문서를 고칩니다.

| 문서 | 무엇을 다루나 | 언제 읽나 |
|---|---|---|
| **README.md** (이 문서) | 설치·실행, 핵심 환경 변수, 테스트·CI, API 목록, 배포 점검 | 처음 받았을 때, 배포 전 |
| [docs/guides/ARCHITECTURE.md](./docs/guides/ARCHITECTURE.md) | 폴더 구조와 배선, 요청·트랜잭션 흐름, DB 세션·라우팅, 설정 로딩, **기동·종료 순서**, **로깅**, 접속 로그, 인증, SQLAdmin, Celery, Alembic, 설계 결정, 전체 설정 부록 | 구조를 이해하거나 런타임(시작·종료·로그)을 건드리기 전 |
| [docs/guides/DEVELOPMENT.md](./docs/guides/DEVELOPMENT.md) | 새 기능·테이블 추가 절차, 세션·DI 선택, 트랜잭션 규칙, ORM(`catalog`)·Raw SQL(`reports`) 실습, Raw SQL 보안, 마이그레이션, 비동기 원칙, 테스트·리뷰 체크리스트 | 코드를 작성할 때 |
| [docs/specs/orm-raw-repository/requirements.md](./docs/specs/orm-raw-repository/requirements.md) | ORM/Raw 이원화 작업의 요구 명세 — 요구 ID(AR·TX·NFR 등)의 원본 | 코드·문서가 인용한 요구 ID 를 찾을 때 |
| [docs/specs/orm-raw-repository/development-plan.md](./docs/specs/orm-raw-repository/development-plan.md) | 같은 작업의 착수 시점 설계·Phase 0~7 계획 | 요구 명세의 Phase 추적표를 따라갈 때 |
| [docs/crp/groups/orm-raw-repository/](./docs/crp/groups/orm-raw-repository/) | 요구·설계 결정(REQ/ADR)·결함 원장·검수 기록 (append-only) | 결정의 근거와 이력을 볼 때 |

- `docs/specs/` 두 문서는 **착수 기준선**이라 내용을 고치지 않습니다. 이후의 확장·변경은 CRP 의
  `design-baseline.md` 에 쌓입니다. `requirements.md` 는 검수 게이트(`scripts/review_gate.py`)가
  요구 ID 선언 원본으로 읽으므로 옮기거나 이름을 바꾸면 게이트 경로도 함께 고칩니다.
- 날짜 이름 폴더(`docs/YYYY-MM-DD/`)는 `.gitignore` 가 제외하는 로컬 작업 기록입니다.
- `README.md` 와 `docs/guides/*.md` 가 백틱으로 적은 파일 경로는 `tests/test_docs_guides.py` 가
  실재하는지 검사합니다.

---

## 특징

- **계층 분리** — View(Router) → Dependency → Service → Repository → `AsyncSession`.
- **명시적 트랜잭션 경계** — 쓰기 핸들러 본문이 응답을 만들기 전에 `await service.commit()` 을
  한 번 호출합니다. 의존성·Repository 는 커밋하지 않습니다(UnitOfWork 없음).
- **읽기/쓰기 세션 분리** — 조회는 `get_read_only_db_session`, 쓰기는 `get_writer_db_session`.
  `DB_ROUTER_ENABLED=true` 면 replica 라우팅과 읽기 세션의 쓰기 차단이 켜집니다.
- **ORM·Raw SQL 두 가지 Repository** — `BaseRepository`(ORM)와 `RawRepositoryBase`(Raw SQL)는
  상속 관계가 없는 평행 계층입니다. 참조 예제: `app/features/catalog/`(ORM),
  `app/features/reports/`(Raw).
- **검증된 기동·종료** — Redis 연결을 startup 에서 확인하고, 종료는 background task → Redis →
  DB 풀 → 로그 큐 flush 순입니다. 정상 종료·startup 실패·취소·`SIGTERM` 모두에서 끝까지 시도하며,
  실제 uvicorn 프로세스를 띄우는 통합 테스트가 이 순서를 고정합니다.
- **비차단 로깅** — 큐 기반 핸들러 + listener 스레드, 출력은 stdout/stderr 뿐(파일 로그 없음).
- **인증** — OAuth2 password flow + JWT access/refresh, bcrypt 해시.
- **문서·관리 화면** — Scalar(`/docs`, `DEBUG=true` 에서만), SQLAdmin(`/admin`, **인증 없음**).
- **결정적 검수** — `scripts/review_gate.py` 와 CI 가 계층 불변식·공개 API 불변·SKIP 0 을 기계로 확인합니다.

## 기술 스택

| 구분 | 기술 |
|---|---|
| Python | 3.14 (`.python-version`, CI 동일). 최소 3.13 — `TypeVar(default=...)` 사용 |
| Web | FastAPI 0.141, Uvicorn 0.34 |
| DB | SQLAlchemy 2.0 async + aiomysql(MySQL), Alembic(pymysql), 테스트는 aiosqlite |
| 검증·설정 | Pydantic v2, pydantic-settings |
| Redis | startup 연결 검증 + Celery broker/backend (redis-py 5) |
| 작업 큐 | Celery 5 (중앙 `app/celery/`) |
| 인증 | PyJWT, bcrypt |
| 관리·문서 | SQLAdmin, Scalar |
| 도구 | uv, pytest(+asyncio·env), ruff, mypy, bandit, pre-commit |

---

## 빠른 시작

모든 명령은 **저장소 루트**에서 실행합니다(`.env` 를 작업 디렉터리 기준으로 읽습니다).

### 0. 무엇이 필요한가

| 실행 방식 | Redis | MySQL | 결과 |
|---|---|---|---|
| `DEBUG=false` | 필요 | 없어도 기동 | `/health` 200, `/ready` 503, DB 를 쓰는 API 는 500, `/docs` 404 |
| `DEBUG=true` (기본값) | 필요 | **필요** | startup 에서 개발용 테이블 생성을 시도하므로 MySQL 이 없으면 기동 실패 |
| 단위 테스트 | 불필요* | 불필요* | *실제 uvicorn 수명 테스트는 Redis, `-m mysql` 테스트는 MySQL 이 없으면 skip |

Redis 는 끌 수 없는 startup 조건입니다(`DEBUG` 와 무관). API 문서(`/docs`)는 `DEBUG=true` 에서만
열리고, `DEBUG=true` 는 MySQL 을 요구합니다 — 첫 실행에서 가장 헷갈리는 조합입니다.

### 1. 의존성 설치

```bash
uv sync
```

`[tool.uv] package = false` 라 루트 패키지는 설치하지 않고 의존성만 설치합니다.

### 2. Redis 만으로 배선 확인

```bash
docker run --rm -d --name fastapi-redis -p 6379:6379 redis:7-alpine
DEBUG=false uv run uvicorn main:app --port 8000
curl http://127.0.0.1:8000/health      # {"status":"healthy","version":"0.1.0"}
```

PowerShell 은 `$env:DEBUG = "false"` 로 지정하고, 끝난 뒤 `Remove-Item Env:DEBUG` 로 되돌립니다.
`compose.test.yaml` 의 Redis 를 써도 됩니다: `docker compose -f compose.test.yaml up -d --wait redis-test`.

### 3. MySQL 추가 — 기능 API·문서까지

```bash
docker run -d --name fastapi-mysql -p 3306:3306 \
  -e MYSQL_ALLOW_EMPTY_PASSWORD=yes -e MYSQL_DATABASE=fastapi_db mysql:8
uv run uvicorn main:app --reload --port 8000
```

설정 기본값(`MYSQL_HOST=localhost`, `MYSQL_USER=root`, `MYSQL_PASSWORD=""`,
`MYSQL_DATABASE=fastapi_db`)에 맞춘 **로컬 전용** 예시입니다(빈 root 비밀번호를 운영에 쓰지 않습니다).
이 단일 컨테이너 경로는 실행 확인하지 않았습니다 — 검증된 것은 `compose.test.yaml`(포트 3308) 경로입니다.
데이터베이스와 계정 권한은 미리 있어야 합니다. `DEBUG=true` 의 테이블 생성은 **없는 테이블만** 만드는
개발 편의 기능이고 migration 이 아닙니다.

### 4. `.env`

```bash
cp .env.example .env        # PowerShell: Copy-Item -LiteralPath .env.example -Destination .env
```

- `.env.example` 은 복사용 견본이지 자동 fallback 이 아닙니다. `.env` 가 없으면 코드 기본값을 씁니다.
- 우선순위: **프로세스 환경 변수 → `.env` → 코드 기본값**.
- `.env.example` 의 `MYSQL_PASSWORD=your_password` 는 3단계의 빈 비밀번호 컨테이너와 맞지 않습니다.
  복사했다면 값을 맞추세요.
- 리스트 값은 JSON 배열로 씁니다: `CORS_ALLOW_ORIGINS=["http://localhost:3000"]`.

### 5. 실행 명령과 접속 주소

```bash
uv run python main.py                                  # run_server(): SERVER_HOST/PORT, reload=DEBUG
uv run uvicorn main:app --reload --host 127.0.0.1 --port 8000   # uvicorn 표준 CLI
```

두 명령 모두 정상이며 오류·traceback 도 똑같이 출력됩니다. 차이는 uvicorn 자신의 로그 포맷뿐입니다
(`python main.py` 는 프로젝트 포맷 + `[app=uvicorn]`). 이유는
[ARCHITECTURE §9.6](./docs/guides/ARCHITECTURE.md#96-실행-명령에-따른-차이).
`--lifespan off` 는 Redis 확인과 자원 정리를 통째로 건너뛰므로 쓰지 않습니다.

| 주소 | 조건 |
|---|---|
| <http://127.0.0.1:8000/health> | 항상 — 프로세스 생존(liveness) |
| <http://127.0.0.1:8000/ready> | 항상 — writer DB `SELECT 1`(2초), 실패 시 503 (readiness) |
| <http://127.0.0.1:8000/docs>, `/openapi.json` | `DEBUG=true` |
| <http://127.0.0.1:8000/admin> | `ADMIN=true`(기본값) — **인증 없음** |

오케스트레이터의 liveness probe 에는 `/health`, readiness probe 에는 `/ready` 를 연결합니다.
`/health` 가 DB 를 검사하면 DB 가 잠깐 흔들릴 때 멀쩡한 프로세스가 재시작됩니다.

### 자주 막히는 지점

| 증상 | 원인 | 조치 |
|---|---|---|
| startup 에서 `Redis 연결 실패: <오류 타입>` | Redis 미기동·주소/포트/비밀번호 오류 | `REDIS_*` 확인. `DEBUG=false` 로 우회되지 않음 |
| startup 에서 `Can't connect to MySQL server` | `DEBUG=true` 가 테이블 생성을 시도 | MySQL 을 띄우거나 `DEBUG=false` |
| `/docs` 404 | `DEBUG=false` 는 문서를 끈다 | `DEBUG=true` (MySQL 필요) |
| 기능 API 만 500 | 앱은 떴지만 DB 가 없다 | 3단계 |
| startup INFO 로그가 안 보임 | `LOG_LEVEL`·`LOG_CONSOLE_LEVEL` 명시값이 더 높음 | [ARCHITECTURE §9.3](./docs/guides/ARCHITECTURE.md#93-레벨이-정해지는-방식) |
| 새 기능 URL 이 404 | `main.py` 에 `include_router` 누락 | [DEVELOPMENT §2](./docs/guides/DEVELOPMENT.md#2-새-기능테이블-추가-절차) |
| MySQL 테스트가 `Access denied` 로만 실패 | 3308 포트를 다른 MySQL 이 선점(IDE 포트 포워딩 등) | Windows `Get-NetTCPConnection -LocalPort 3308`, Linux `ss -ltn`. `MYSQL_TEST_PORT` 로 이동 |
| 통합 테스트가 갑자기 전부 skip | WSL2 유휴로 VM 과 컨테이너가 내려감(`docker ps -a` 에 `Exited (0)`) | `docker compose -f compose.test.yaml up -d --wait` |

---

## 환경 변수

처음에 의미 있는 것만 적습니다. 모든 필드·기본값·소비 지점은
[ARCHITECTURE 부록](./docs/guides/ARCHITECTURE.md#부록-설정-필드-전체)에 있고,
`config.py` 와 `.env.example` 은 `tests/core/test_settings_contract.py` 가 양방향으로 맞춰 둡니다.

| 변수 | 기본값 | 의미 |
|---|---|---|
| `DEBUG` | `true` | true: DEBUG 로그 기본값·개발용 테이블 생성·`/docs`·`python main.py` reload. false: 모두 끔 |
| `ADMIN` | `true` | `/admin` 마운트. **인증 없음**, `DEBUG` 와 독립 |
| `ENV` | `development` | `development`/`test`/`staging`/`production` — 로그 출력 구성(시간대·stderr)에 사용 |
| `SERVER_HOST` / `SERVER_PORT` | `0.0.0.0` / `8000` | `python main.py` 전용 바인딩 |
| `MYSQL_HOST`·`MYSQL_PORT`·`MYSQL_USER`·`MYSQL_PASSWORD`·`MYSQL_DATABASE` | `localhost`·`3306`·`root`·`""`·`fastapi_db` | primary(writer) |
| `DB_ROUTER_ENABLED` / `DB_REPLICATION_ENABLED` | `false` / `false` | 읽기/쓰기 라우팅, replica 사용(모순 조합은 기동 시 거부) |
| `REDIS_HOST`·`REDIS_PORT`·`REDIS_DB`·`REDIS_PASSWORD` | `localhost`·`6379`·`0`·없음 | startup ping 대상 + Celery broker/backend |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` | JWT 서명 키 — **배포 전 반드시 교체** |
| `LOG_LEVEL` / `LOG_CONSOLE_LEVEL` | 없음 | 없으면 `DEBUG` 에 따라 DEBUG/INFO |
| `LOG_SQL_ECHO_ENABLED` | `false` | SQL 과 **바인딩 값** 로깅. 운영에서 켜지 않음 |
| `ACCESS_LOG_ENABLED` | `true` | 요청마다 접속 로그를 DB 에 저장 |
| `CORS_ALLOW_ORIGINS` / `CORS_ALLOW_CREDENTIALS` | `["*"]` / `false` | 와일드카드 + credentials 조합은 기동 시 거부 |

---

## 테스트·검수·CI

### 실행

```bash
uv run python -m pytest                        # 전체. MySQL·Redis 가 없으면 해당 테스트는 skip
uv run python -m pytest -m "not mysql"         # CI gate job 과 같은 집합
uv run ruff check . && uv run ruff format --check .
uv run mypy .                                  # 판정용은 콜드 캐시(CI 는 캐시를 복원하지 않는다)

docker compose -f compose.test.yaml up -d --wait   # MySQL 8.4(127.0.0.1:3308) + Redis 7(6379)
uv run python -m pytest -m mysql --mysql-required  # MySQL 에 닿지 못하면 skip 이 아니라 실패
docker compose -f compose.test.yaml down -v        # 정리(MySQL 데이터는 tmpfs)
```

- `pytest` 콘솔 스크립트 대신 `python -m pytest` 를 씁니다. 콘솔 스크립트가 다른 인터프리터를 집어
  import 가 어긋난 전례가 있고, CI 도 같은 형태입니다. 저장소 안 임시 디렉터리가 필요하면
  `--basetemp .pytest_tmp`(git 무시 대상)를 줍니다.
- 테스트 위치: 기능 테스트는 `app/features/<name>/tests/`, core 계약·배선·교차 기능·통합 테스트는
  최상위 `tests/`. `pyproject.toml` 이 `DEBUG=true`, `ENV=test` 로 실행합니다.
- **skip 은 통과가 아닙니다.** 결과 줄의 `skipped` 를 확인하세요. 실제 uvicorn 수명 테스트
  (`tests/integration/test_uvicorn_lifecycle.py`)는 `REDIS_HOST`/`REDIS_PORT` 에 닿지 못하면,
  `-m mysql` 테스트는 3308 에 MySQL 이 없으면 skip 됩니다. 통합 결과를 근거로 쓰는 자리에서는
  `--mysql-required` 를 붙입니다.
- 3308 이 이미 쓰이면 `MYSQL_TEST_PORT=3311` 을 compose 와 pytest 에 함께 줍니다. 로컬 6379 가
  쓰이면 `REDIS_TEST_PORT=6380` 으로 올리고 테스트에 `REDIS_PORT=6380` 을 줍니다.

### 검수 게이트

```bash
uv run python -m scripts.review_gate          # 전체
uv run python -m scripts.review_gate --fast   # pytest 제외
```

| 검사 | 무엇을 보나 |
|---|---|
| pytest · ruff check · ruff format · mypy | 도구 4종 (`--fast` 는 pytest 제외) |
| 계층 불변식 INV-1·2·5 | View 가 SQL/세션을 직접 다루지 않음, Repository·Dependency 가 커밋하지 않음, Raw Base 가 ORM Base 를 상속하지 않음 — AST 로 확인 |
| 공개 API 불변 INV-11 | `docs/crp/groups/orm-raw-repository/baseline/openapi.json` 대비 경로·성공 상태 코드 제거·변경 |
| MySQL 테스트 포트 단일 출처 | `compose.test.yaml`·`tests/integration/conftest.py`·charter 의 기본 포트 일치 |
| 문서 인용 커밋 도달성 | CRP 문서가 인용한 커밋 해시가 HEAD 에서 도달 가능 |
| 인용 요구 ID 실재 | 코드·문서가 인용한 REQ/ADR/NFR 등이 `requirements.md`·CRP 에 선언됨 |
| path operation INV-10 | 전 엔드포인트가 `async def` 이고 요청 경로에 동기 I/O 가 없음 |
| 취소·프로세스 종료 테스트 실재 | 종료 계약 테스트 5건이 삭제·개명되지 않고 수집됨 |
| charter 인수기준 ↔ 수렴 선언 | 기준이 열린 채 "수렴" 을 선언하지 않음 |

### CI (`.github/workflows/ci.yml`)

| job | 내용 |
|---|---|
| `gate` | `uv sync --frozen` → ruff(lint·format) → mypy(콜드 캐시) → bandit(MEDIUM 이상, `app`·`main.py`·`config.py`) → compose 의 `redis-test` 기동 → `pytest -m "not mysql" -rsxX` → **skipped/xfailed/xpassed 가 있으면 실패** → `alembic heads` 단일 head 확인 |
| `mysql` | compose 의 `mysql-test` 기동 → `pytest -m mysql --mysql-required` → skip 또는 0건이면 실패 |

두 job 은 테스트 집합이 정확히 상보입니다. 배포·이미지 빌드는 이 저장소 범위 밖입니다.
커밋 전 훅은 `.pre-commit-config.yaml`(ruff·ruff-format·기본 위생 검사)에 있습니다.

---

## API

`app.openapi()` 로 확인한 전량 — **23 경로 / 38 오퍼레이션**. 모든 기능 API 는 `/api/v1/<기능명>/…`
형태이며, `tests/test_route_inventory.py` 가 경로·메서드를 고정합니다(새 라우트를 추가하면 그 테스트와
이 표를 함께 갱신). 요청·응답 형식은 `DEBUG=true` 의 `/docs` 에서 봅니다.

| 태그 | 메서드·경로 | 비고 |
|---|---|---|
| Health | `GET /health` · `GET /ready` | liveness / readiness(503) |
| Home | `GET /api/v1/home/access-logs` · `/recent` · `/by-ip/{ip_address}` · `/by-user/{user_id}` · `/stats` | 접속 로그 조회(전부 읽기 세션) |
| Blog | `GET·POST /api/v1/blog/posts` · `GET·PATCH·DELETE /api/v1/blog/posts/{post_id}` | CRUD |
| Reply | `GET·POST /api/v1/reply/replies` · `GET·PATCH·DELETE /api/v1/reply/replies/{reply_id}` | CRUD |
| SNS | `GET·POST /api/v1/sns/posts` · `GET·PATCH·DELETE /api/v1/sns/posts/{post_id}` | CRUD |
| User | `GET·POST /api/v1/user/users` · `GET·PATCH·DELETE /api/v1/user/users/{user_id}` | CRUD |
| Auth | `POST /api/v1/auth/register` · `POST /api/v1/auth/login`(form) · `POST /api/v1/auth/refresh` · `GET /api/v1/auth/me`(Bearer) | [ARCHITECTURE §11](./docs/guides/ARCHITECTURE.md#11-인증-jwt) |
| Catalog | `GET·POST /api/v1/catalog/products` · `GET·PATCH·DELETE /api/v1/catalog/products/{product_id}` | ORM 참조 예제 |
| Reports | `GET /api/v1/reports/sales/daily` · `POST /api/v1/reports/sales/daily/snapshots` | Raw SQL 참조 예제(조회·적재) |

DELETE 는 204(본문 없음)입니다. 오류 응답은 `{"error_code", "message", "detail"}` 형식입니다.
기능 API 는 기본적으로 인증을 요구하지 않습니다(`auth/me` 제외) — 새 엔드포인트의 인증·권한은
직접 명시합니다.

---

## 운영 배포 체크리스트

**앱은 아래 조합을 막지 않습니다(확정 정책, 2026-08-12).** `ENV=production` 과 `ADMIN=true` 를 함께
줘도 기동은 성공합니다. 개발 기본값을 유지하는 대신 차단 책임을 배포 쪽에 둡니다.

| # | 확인 | 빠뜨리면 |
|---|---|---|
| 1 | `ADMIN=false` 를 **명시**했는가 | 기본값 `true` 라 인증 없는 `/admin` 이 열린다 — 사용자·게시글·댓글·접속로그 조회·수정·삭제와 CSV 내보내기 가능(비밀번호 해시만 제외) |
| 2 | 외부 노출이 필요 없으면 `SERVER_HOST=127.0.0.1` 인가 (`python main.py` 실행 시) | 기본값 `0.0.0.0` |
| 3 | 리버스 프록시·방화벽이 `/admin` 을 막는가 | 1·2 가 뚫리면 마지막 방어선이 없다 |
| 4 | `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`(서로 다른 값)를 교체했는가 | 기본값이면 누구나 토큰을 위조한다 |
| 5 | `DEBUG=false` 인가 | `/docs`·`/openapi.json` 공개, 500 응답에 예외 문자열 노출, worker 마다 startup 에서 `create_all` 시도 |
| 6 | 스키마를 `alembic upgrade head` 로 먼저 적용했는가 | `DEBUG=false` 는 테이블을 만들지 않는다 |
| 7 | `CORS_ALLOW_ORIGINS` 를 실제 출처로 좁혔는가 | 기본값 `["*"]` |
| 8 | `LOG_SQL_ECHO_ENABLED=false` 인가 | SQL 바인딩 값(해시·토큰·검색어)이 로그 수집기로 나간다 |
| 9 | Redis 가 준비됐고, 컨테이너 종료 유예 시간이 종료 예산보다 긴가 | Redis 없으면 기동 실패 / 유예가 짧으면 정리 도중 SIGKILL ([ARCHITECTURE §8.2](./docs/guides/ARCHITECTURE.md#82-시간-예산)) |
| 10 | worker 수 × DB 풀 크기가 DB 최대 연결 수 안인가 | [ARCHITECTURE §4.1](./docs/guides/ARCHITECTURE.md#41-엔진과-커넥션-풀) |

1과 2는 곱해집니다. 기본값이 각각 `true` 와 `0.0.0.0` 이라, 아무것도 설정하지 않은 배포가 정확히
"인증 없는 관리 화면이 네트워크에 열린" 상태입니다. 서버 측 토큰 폐기 목록은 없으므로 유출된 refresh
토큰은 만료(`REFRESH_TOKEN_EXPIRE_DAYS`, 기본 7일)까지 유효합니다.

---

## 참고 자료

- [FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/) ·
  [Pydantic](https://docs.pydantic.dev/latest/) · [Alembic](https://alembic.sqlalchemy.org/)

## 라이선스

MIT License
