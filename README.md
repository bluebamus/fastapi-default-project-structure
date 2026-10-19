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

| 문서 | 역할 | 언제 보나 |
|---|---|---|
| **README.md** (이 문서) | 개요 · 빠른 시작 · 문서 안내(유일한 색인). 핵심 환경 변수, 테스트·CI, API 목록, 배포 점검 | 처음 받았을 때, 배포 전 |
| [docs/guides/ARCHITECTURE.md](./docs/guides/ARCHITECTURE.md) | 구조 · 런타임 동작 레퍼런스 — 배선, 요청·트랜잭션 흐름, DB 세션·라우팅, 설정, 기동·종료 순서와 예산, 로깅, 접속 로그, 인증, SQLAdmin, Celery, Alembic, 설계 결정, 전체 설정 부록 | 구조를 이해하거나 런타임(시작·종료·로그)을 건드리기 전 |
| [docs/guides/DEVELOPMENT.md](./docs/guides/DEVELOPMENT.md) | 기능 개발 가이드 — 새 기능·테이블 추가 절차, 세션·DI 선택, 트랜잭션 규칙, ORM(`catalog`)·Raw SQL(`reports`) 실습, 마이그레이션, 비동기 원칙, 테스트·리뷰 체크리스트 | 코드를 작성할 때 |
| [docs/guides/server-lifecycle-guide.html](./docs/guides/server-lifecycle-guide.html) | 서버 수명주기 안내서 — 설정 → 기동 → 요청 → 종료를 도식과 함께 추적(상세 표는 ARCHITECTURE) | 서버가 뜨고 끝나는 흐름을 한 번에 따라가 볼 때 |
| [docs/guides/feature-development-guide.html](./docs/guides/feature-development-guide.html) | 신규 뷰·테이블 개발 안내서 — 상품 생성 한 요청을 따라가며 계층·DI·트랜잭션을 설명(절차 원본은 DEVELOPMENT) | 새 기능을 처음 만들 때 |
| [docs/guides/admin-auth-guide.html](./docs/guides/admin-auth-guide.html) | 관리 화면 인증 안내서 — `/admin` 로그인(서명 세션 쿠키)과 API 인증(JWT)의 범위, 구성·기동·로그인·요청별 확인·로그아웃 흐름도, 쿠키 속성, 계정 수명주기, 위협 모델, 운영·문제 해결 | 관리 화면 인증을 이해하거나 바꾸기 전, 배포 전 |
| [docs/specs/orm-raw-repository/requirements.md](./docs/specs/orm-raw-repository/requirements.md) | 고정 기준선(착수 명세) — 요구 ID(AR·TX·NFR 등)의 원본 | 코드·문서가 인용한 요구 ID 를 찾을 때 |
| [docs/specs/orm-raw-repository/development-plan.md](./docs/specs/orm-raw-repository/development-plan.md) | 고정 기준선 — 착수 시점 설계·Phase 0~7 계획 | 요구 명세의 Phase 추적표를 따라갈 때 |
| [docs/specs/orm-raw-repository/workflow-guide.md](./docs/specs/orm-raw-repository/workflow-guide.md) | 고정 기준선 — 착수 시점 구현 지침·예시 코드 | 착수 당시의 지침과 현재를 비교할 때 |
| [docs/crp/groups/orm-raw-repository/](./docs/crp/groups/orm-raw-repository/) | 검수 이력(append-only) — 요구·설계 결정(REQ/ADR)·결함 원장·검수 기록 | 결정의 근거와 이력을 볼 때 |
| [docs/crp/groups/service-hardening/](./docs/crp/groups/service-hardening/) | 검수 이력(append-only) — 2026-10-12 서비스 하드닝(CI·DSN·접속 로그·UTC·Redis·인증/인가) 단계 A~F2 의 요구·결정·원장. REQ/ADR 번호는 그룹 안에서만 유효 | 하드닝 단계의 근거를 볼 때 |
| [docs/crp/groups/admin-login/](./docs/crp/groups/admin-login/) | 검수 이력(append-only) — 2026-10-12 관리 화면 로그인(슈퍼유저·Bootstrap 화면)·`ADMIN_DISABLED`·세션 범위·배포 전 할 일 문서화의 요구·결정·원장 | 관리 화면 인증 결정의 근거를 볼 때 |
| [docs/crp/groups/security-ops-hardening/](./docs/crp/groups/security-ops-hardening/) | 검수 이력(append-only) — 2026-10-19 DB 오류 바인드 값 숨김 회귀·접속 로그 보존(beat)·관리 로그인 CSRF·`created_at` 날짜 필터의 요구·결정·원장 | 보안·운영 보강의 근거를 볼 때 |

- `docs/specs/` 세 문서는 **고정 기준선**이라 내용을 고치지 않습니다(경로·이름 정정만). 현재 동작은
  `docs/guides/` 가, 이후의 확장·변경은 CRP 의 `design-baseline.md` 가 담습니다. `requirements.md` 는
  검수 게이트(`scripts/review_gate.py`)가 요구 ID 선언 원본으로 읽으므로 옮기거나 이름을 바꾸면 게이트
  경로도 함께 고칩니다.
- HTML 안내서는 흐름 요약이고(관리 화면 인증 안내서는 그 주제의 원본이다), 같은 사실의 상세 표는 Markdown 가이드가 소유합니다. 한쪽을 고치면
  다른 쪽도 함께 고칩니다.
- 날짜 이름 폴더(`docs/YYYY-MM-DD/`)는 `.gitignore` 가 제외하는 로컬 작업 기록입니다.
- `README.md` 와 `docs/guides/` 의 Markdown·HTML 이 백틱(HTML 은 `<code>`)으로 적은 파일 경로는
  `tests/test_docs_guides.py` 가 실재하는지 검사합니다.

---

## 특징

- **계층 분리** — View(Router) → Dependency → Service → Repository → `AsyncSession`.
- **명시적 트랜잭션 경계** — 쓰기 핸들러 본문이 응답 DTO 를 검증한 뒤 `await service.commit()` 을
  한 번 호출하고 응답을 반환합니다. 의존성·Repository 는 커밋하지 않습니다(UnitOfWork 없음).
- **읽기/쓰기 세션 분리** — 조회는 `get_read_only_db_session`, 쓰기는 `get_writer_db_session`.
  읽기 세션의 쓰기 차단은 `DB_ROUTER_ENABLED` 와 무관하게 항상 동작하고,
  `DB_ROUTER_ENABLED=true` 면 여기에 replica 라우팅이 더해집니다.
- **ORM·Raw SQL 두 가지 Repository** — `BaseRepository`(ORM)와 `RawRepositoryBase`(Raw SQL)는
  상속 관계가 없는 평행 계층입니다. 참조 예제: `app/features/catalog/`(ORM),
  `app/features/reports/`(Raw).
- **검증된 기동·종료** — Redis 연결을 startup 에서 확인하고, 종료는 background task → Redis →
  DB 풀 → 로그 큐 flush 순입니다. 정상 종료·startup 실패·취소·`SIGTERM` 모두에서 끝까지 시도하며,
  실제 uvicorn 프로세스를 띄우는 통합 테스트가 이 순서를 고정합니다.
- **비차단 로깅** — 큐 기반 핸들러 + listener 스레드, 출력은 stdout/stderr 뿐(파일 로그 없음).
  메시지·traceback(체인 예외 포함)·`stack_info` 의 비밀값(DSN 비밀번호·`password=`·`Authorization`)은 출력 전에
  `***` 로 가립니다 — `uvicorn main:app` CLI 와 Celery worker 의 핸들러도 같은 규칙입니다.
- **인증** — OAuth2 password flow + JWT access/refresh. Argon2id 해시(기존 bcrypt 는 로그인 때 재해시),
  refresh 회전·재사용 탐지·로그아웃(Redis), 로그인·가입 레이트 리밋(429 + `Retry-After`).
- **인가** — 슈퍼유저/일반 2단계. 게시글·피드·댓글 쓰기는 로그인, 수정·삭제는 작성자 또는 슈퍼유저, 관리 경로
  (상품 쓰기·리포트·접속 로그·사용자 관리)는 슈퍼유저. 첫 관리자는 `python -m scripts.create_superuser` 로 만든다.
- **문서·관리 화면** — Scalar(`/docs`, `DEBUG=true` 에서만), SQLAdmin(`/admin`, **활성 슈퍼유저 로그인** —
  Bootstrap 로그인 화면·CSRF 토큰·서명 세션 쿠키·레이트 리밋, 목록의 `created_at` 날짜 필터. 쓰지 않으면
  `ADMIN_DISABLED=true` 로 흔적 없이 끈다).
  관리 세션은 `/admin` 전용이고 API 인증(JWT)과 섞이지 않는다([관리 화면 인증 안내서](./docs/guides/admin-auth-guide.html)).
- **결정적 검수** — `scripts/review_gate.py` 와 CI 가 계층 불변식·공개 API 불변·SKIP 0 을 기계로 확인합니다.

## 기술 스택

| 구분 | 기술 |
|---|---|
| Python | 3.14 (`.python-version`, CI 동일). 최소 3.13 — `TypeVar(default=...)` 사용 |
| Web | FastAPI 0.141, Uvicorn 0.54 |
| DB | SQLAlchemy 2.0 async + aiomysql(MySQL), Alembic(pymysql), 테스트는 aiosqlite |
| 검증·설정 | Pydantic v2, pydantic-settings |
| Redis | 필수 — **서버 6.2 이상**(`GETDEL` 이 쓰는 명령 중 가장 높은 요구치, 기동 시 `INFO server` 로 확인해 미만이면 기동 거부) · startup 연결 검증 · `/ready` 판정 · 주입 provider `get_redis`(refresh 회전 기록·레이트 리밋) + Celery broker/backend (클라이언트 redis-py 6, 선언은 `>=6.0.0,<7.0.0` — 실제 해석 천장은 `kombu[redis]` 가 정한다) |
| 작업 큐 | Celery 5 (앱 `app/celery/`, 태스크는 기능별 `app/features/<name>/tasks.py` 자동 발견) |
| 인증 | PyJWT, pwdlib[argon2](Argon2id), bcrypt(이전 해시 검증 전용) — 테스트는 fakeredis |
| 관리·문서 | SQLAdmin(로그인 화면 Bootstrap 5.3 — CDN·SRI, 세션 쿠키 서명은 itsdangerous), Scalar |
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

Redis 는 끌 수 없는 startup 조건이고 서버는 **6.2 이상**이어야 합니다(`DEBUG` 와 무관). API 문서(`/docs`)는 `DEBUG=true` 에서만
열리고, `DEBUG=true` 는 MySQL 을 요구합니다 — 첫 실행에서 가장 헷갈리는 조합입니다.

### 1. 의존성 설치

```bash
uv sync
```

`[tool.uv] package = false` 라 루트 패키지는 설치하지 않고 의존성만 설치합니다.

### 2. `.env` 준비 — 먼저 채운다

```bash
cp .env.example .env        # PowerShell: Copy-Item -LiteralPath .env.example -Destination .env
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"   # 키마다 한 번씩, 세 번 실행
```

`.env` 에서 아래를 바꿉니다. 바꾸지 않으면 **개발 환경에서도 기동하지 않습니다**(설정 검사, ADR-045).
오류 메시지에 고칠 설정 이름이 나오므로 그대로 따라 고치면 됩니다.

| 설정 | 할 일 |
|---|---|
| `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`·`SESSION_SECRET_KEY` | 위 명령으로 만든 값을 **서로 다르게** 넣는다(32자 이상) |
| `MYSQL_PASSWORD` | 4단계에서 띄울 MySQL 의 비밀번호와 같은 값. 비워 두거나 예시 값이면 거부 |
| `SMTP_PASSWORD` | 메일을 안 쓰면 **비운다**. 예시 값을 남겨 두면 거부 |

- `.env` 가 없으면 기동하지 않습니다. 파일 없이 환경 변수로 주입하는 경우(컨테이너)는 `ENV`·비밀 키 3종·
  `MYSQL_HOST/USER/PASSWORD/DATABASE` 가 모두 있어야 합니다.
- 우선순위: **프로세스 환경 변수 → `.env` → 코드 기본값**. 코드 기본값은 그대로 두되, 예시 값·빈 비밀번호로는 뜨지 않습니다.
- 리스트 값은 JSON 배열로 씁니다: `CORS_ALLOW_ORIGINS=["http://localhost:3000"]`.
- 테스트(`ENV=test`, pytest 가 지정)는 이 검사를 하지 않습니다 — `.env` 없이 돕니다.

### 3. Redis 만으로 배선 확인

```bash
docker run --rm -d --name fastapi-redis -p 6379:6379 redis:7-alpine   # 6.2 이상이면 된다
DEBUG=false uv run uvicorn main:app --port 8000
curl http://127.0.0.1:8000/health      # {"status":"healthy","version":"0.1.0"}
```

PowerShell 은 `$env:DEBUG = "false"` 로 지정하고, 끝난 뒤 `Remove-Item Env:DEBUG` 로 되돌립니다.
`compose.test.yaml` 의 Redis 를 써도 됩니다: `docker compose -f compose.test.yaml up -d --wait redis-test`.

### 4. MySQL 추가 — 기능 API·문서까지

```bash
docker run -d --name fastapi-mysql -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD='<.env 의 MYSQL_PASSWORD 와 같은 값>' -e MYSQL_DATABASE=fastapi_db mysql:8
uv run uvicorn main:app --reload --port 8000
```

설정 기본값(`MYSQL_HOST=localhost`, `MYSQL_USER=root`, `MYSQL_DATABASE=fastapi_db`)에 맞춘 **로컬 전용**
예시입니다. 빈 비밀번호는 개발 환경에서도 설정 검사가 거부하므로 비밀번호를 지정합니다.
이 단일 컨테이너 경로는 실행 확인하지 않았습니다 — 검증된 것은 `compose.test.yaml`(포트 3308) 경로입니다.
데이터베이스와 계정 권한은 미리 있어야 합니다. `DEBUG=true` 의 테이블 생성은 **없는 테이블만** 만드는
개발 편의 기능이고 migration 이 아닙니다.

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
| <http://127.0.0.1:8000/ready> | 항상 — writer DB `SELECT 1` 과 Redis `PING`(각 2초, 동시에), 하나라도 실패 시 503 (readiness) |
| <http://127.0.0.1:8000/docs>, `/openapi.json` | `DEBUG=true` |
| <http://127.0.0.1:8000/admin> | `ADMIN_DISABLED=false`(기본값) — **활성 슈퍼유저 로그인 필요**(아래). `ADMIN_DISABLED=true` 면 404 |

관리 화면에 들어가려면 MySQL 이 뜬 상태에서 슈퍼유저를 하나 만들고(비밀번호를 두 번 묻는다) 그 계정으로
`/admin/login` 의 Bootstrap 로그인 화면에서 로그인합니다(폼에 CSRF 토큰이 숨은 필드로 실린다 — 화면을 오래 열어 두었다가
세션이 바뀌면 "요청이 만료되었습니다" 403 이 나오고, 다시 그려진 화면에서 그대로 다시 로그인하면 된다):

```bash
uv run python -m scripts.create_superuser --username admin --email admin@example.com
```

오케스트레이터의 liveness probe 에는 `/health`, readiness probe 에는 `/ready` 를 연결합니다.
`/health` 가 DB 를 검사하면 DB 가 잠깐 흔들릴 때 멀쩡한 프로세스가 재시작됩니다.

### 자주 막히는 지점

| 증상 | 원인 | 조치 |
|---|---|---|
| startup 에서 `Redis 연결 실패: <오류 타입>` | Redis 미기동·주소/포트/비밀번호 오류 | `REDIS_*` 확인. `DEBUG=false` 로 우회되지 않음 |
| startup 에서 `Redis <버전> 는 지원하지 않는다 — 최소 6.2.0 이상이 필요하다` | Redis 서버가 6.2 미만이라 `GETDEL`(refresh 회전)이 없다 | Redis 를 6.2 이상으로 올린다. `INFO` 를 막아 둔 관리형 Redis 는 WARNING 만 남기고 뜬다 — 그때는 버전을 직접 확인한다 |
| startup 에서 `Can't connect to MySQL server` | `DEBUG=true` 가 테이블 생성을 시도 | MySQL 을 띄우거나 `DEBUG=false` |
| `/docs` 404 | `DEBUG=false` 는 문서를 끈다 | `DEBUG=true` (MySQL 필요) |
| 기능 API 만 500 | 앱은 떴지만 DB 가 없다 | 4단계 |
| `.env 파일이 없고, 필수 설정이 …` | `.env` 가 없다 | 2단계. 컨테이너라면 메시지에 나온 환경 변수를 주입 |
| `ENV=development 설정 검사 실패 — X 가 예시 값…` | `.env` 의 비밀 키·비밀번호가 예시 값·빈 값·32자 미만 | 2단계 표대로 X 를 고친다 |
| `설정 ADMIN 은 ADMIN_DISABLED 로 바뀌었습니다` | 환경 변수나 `.env` 에 예전 `ADMIN` 이 남아 있다(옛 `.env.example` 사본) | 그 줄을 지운다. `ADMIN=false` 였다면 대신 `ADMIN_DISABLED=true` |
| `/admin` 로그인이 계속 로그인 화면으로 돌아온다 | 계정이 슈퍼유저·활성이 아니거나, HTTP 로 접속했는데 `ENV=staging/production` 이라 쿠키가 `Secure` | `scripts.create_superuser` 로 승격, 배포 환경은 HTTPS 로 접속([관리 화면 인증 안내서](./docs/guides/admin-auth-guide.html#ops)) |
| `/admin/login` 이 429 | 같은 IP+사용자명 5회·같은 IP 20회(60초 창) 초과 | `Retry-After` 초만큼 기다린다. 프록시 뒤인데 모두가 막히면 `TRUSTED_PROXY_HOPS` |
| startup INFO 로그가 안 보임 | `LOG_LEVEL`·`LOG_CONSOLE_LEVEL` 명시값이 더 높음 | [ARCHITECTURE §9.3](./docs/guides/ARCHITECTURE.md#93-레벨이-정해지는-방식) |
| 새 기능 URL 이 404 | `main.py` 에 `include_router` 누락 | [DEVELOPMENT §2](./docs/guides/DEVELOPMENT.md#2-새-기능테이블-추가-절차) |
| MySQL 테스트가 `Access denied` 로만 실패 | 3308 포트를 다른 MySQL 이 선점(IDE 포트 포워딩 등) | Windows `Get-NetTCPConnection -LocalPort 3308`, Linux `ss -ltn`. `MYSQL_TEST_PORT` 로 이동 |
| 통합 테스트가 갑자기 전부 skip | WSL2 유휴로 VM 과 컨테이너가 내려감(`docker ps -a` 에 `Exited (0)`) | `docker compose -f compose.test.yaml up -d --wait` |

---

## 환경 변수

처음에 의미 있는 것만 적습니다. 모든 필드·기본값·소비 지점은
[ARCHITECTURE 부록](./docs/guides/ARCHITECTURE.md#부록-설정-필드-전체)에 있고,
`config.py` 와 `.env.example` 은 `tests/core/test_settings_contract.py` 가 양방향으로 맞춰 둡니다.

`config` import 시점의 설정 검사(ADR-027·028·030·045)가 잘못된 설정을 `RuntimeError` 로 알립니다. 메시지에는 설정 이름만 나오고 값은 나오지 않으며, 위반은 한 번에 모아 보여 줍니다. `ENV=test` 는 검사하지 않습니다.

| 검사 | 적용 ENV |
|---|---|
| `.env` 가 없고 `ENV`·비밀 키 3종·`MYSQL_HOST/USER/PASSWORD/DATABASE` 가 환경 변수로도 없음(`validate_env_source()`) | test 외 전부 |
| `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`·`SESSION_SECRET_KEY`·`MYSQL_PASSWORD` 가 예시 값(`change-this` 포함·`your-` 시작·빈 값) | test 외 전부 |
| `REDIS_PASSWORD`·`SMTP_PASSWORD` 가 **값이 있는데** 예시 값(빈 값은 "안 쓴다" 로 통과) | test 외 전부 |
| 비밀 키 3종이 32자 미만, access 와 refresh 가 같음 | test 외 전부 |
| `DEBUG=true`, `LOG_LEVEL=DEBUG` | staging·production |
| 예전 설정 `ADMIN` 이 환경 변수·`.env` 에 남아 있음(`validate_no_legacy_admin()` — `ADMIN_DISABLED` 로 교체됨) | test 외 전부 |

키는 키마다 따로 만듭니다: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"`

| 변수 | 기본값 | 의미 |
|---|---|---|
| `DEBUG` | `true` | true: DEBUG 로그 기본값·개발용 테이블 생성·`/docs`·`python main.py` reload. false: 모두 끔 |
| `ADMIN_DISABLED` | `false` | false: `/admin` 마운트(활성 슈퍼유저 로그인 필요). true: 관리 화면을 완전히 끈다 — 404, 응답·로그에 경로 없음. `DEBUG` 와 독립 |
| `ENV` | `development` | `development`/`test`/`staging`/`production` — 로그 출력 구성(시간대·stderr)과 설정 검사 범위(위 표) |
| `SERVER_HOST` / `SERVER_PORT` | `0.0.0.0` / `8000` | `python main.py` 전용 바인딩 |
| `MYSQL_HOST`·`MYSQL_PORT`·`MYSQL_USER`·`MYSQL_PASSWORD`·`MYSQL_DATABASE` | `localhost`·`3306`·`root`·`""`·`fastapi_db` | primary(writer) |
| `DB_ROUTER_ENABLED` / `DB_REPLICATION_ENABLED` | `false` / `false` | 읽기/쓰기 라우팅, replica 사용(모순 조합은 기동 시 거부) |
| `REDIS_HOST`·`REDIS_PORT`·`REDIS_DB`·`REDIS_PASSWORD` | `localhost`·`6379`·`0`·없음 | startup ping·버전 확인(6.2 이상)·`/ready` 대상 + refresh 회전 기록·레이트 리밋 + Celery broker/backend |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` / `SESSION_SECRET_KEY` | `change-this-...` | access·refresh 토큰 서명 키와 관리 화면 세션 쿠키(`admin_session`) 서명 키 — 예시 값·32자 미만·access==refresh 면 test 외 **기동 거부**. `SESSION_SECRET_KEY` 를 바꾸면 관리 세션이 모두 끊긴다 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | `15` / `7` | access 는 서버에서 폐기할 수 없으므로 짧게. refresh 는 회전·폐기된다 |
| `JWT_ALGORITHM` / `JWT_ISSUER` / `JWT_AUDIENCE` / `JWT_LEEWAY_SECONDS` | `HS256` / 프로젝트 이름 / 프로젝트 이름`-api` / `10` | 알고리즘은 `HS256`·`HS384`·`HS512` 만. `iss`·`aud` 는 검증 시 일치 필수 |
| `AUTH_LOGIN_MAX_ATTEMPTS` / `AUTH_LOGIN_IP_MAX_ATTEMPTS` / `AUTH_LOGIN_WINDOW_SECONDS` | `5` / `20` / `60` | 로그인 시도 한도(IP+사용자명 / IP, 창 초). 초과 시 429 + `Retry-After`. 관리 화면 로그인도 같은 한도(카운터는 따로) |
| `AUTH_REGISTER_MAX_ATTEMPTS` / `AUTH_REGISTER_WINDOW_SECONDS` | `5` / `3600` | 회원가입 시도 한도(IP) |
| `LOG_LEVEL` / `LOG_CONSOLE_LEVEL` | 없음 | 없으면 `DEBUG` 에 따라 DEBUG/INFO |
| `LOG_SQL_ECHO_ENABLED` | `false` | SQL 과 **바인딩 값** 로깅. 운영에서 켜지 않음 |
| `ACCESS_LOG_ENABLED` | `true` | 요청마다 접속 로그를 DB 에 저장 |
| `TRUSTED_PROXY_HOPS` | `0` | 접속 로그·로그인 레이트 리밋의 IP 를 `X-Forwarded-For` 오른쪽에서 몇 번째로 읽을지(앞단 신뢰 프록시 수). 0 이면 헤더를 보지 않는다. **프록시 뒤 배포는 단수만큼 설정** — 0 이면 전원이 프록시 IP 하나로 보여 한 사람으로 취급되고, 크게 잡으면 IP 위조가 가능하다 |
| `ACCESS_LOG_SENSITIVE_QUERY_KEYS` | `password`·`token`·… | 접속 로그에 값을 `***` 로 저장할 쿼리스트링 키 |
| `ACCESS_LOG_RETENTION_DAYS` | `365` | 접속 로그 보존 일수. Celery beat 가 매일 03:30(`TIME_ZONE`) 이보다 오래된 행을 5,000행씩 지운다. `0` 이면 지우지 않는다, 음수는 기동 시 검증 오류. **beat 를 띄워야 동작**(아래 체크리스트 11) |
| `CORS_ALLOW_ORIGINS` / `CORS_ALLOW_CREDENTIALS` | `["*"]` / `false` | 와일드카드 + credentials 조합은 기동 시 거부 |

---

## 테스트·검수·CI

### 실행

```bash
uv run python -m pytest                        # 전체. MySQL·Redis 가 없으면 해당 테스트는 skip
uv run python -m pytest -m "not mysql"         # CI gate job 과 같은 집합
uv run ruff check . && uv run ruff format --check .
uv run mypy .                                  # 판정용은 콜드 캐시(CI 는 캐시를 복원하지 않는다)

docker compose -f compose.test.yaml up -d --wait   # MySQL 8.4(127.0.0.1:3308) + Redis 7(6379, 앱 최소 6.2)
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
| pytest · ruff check · ruff format · mypy | 도구 4종 (`--fast` 는 pytest 제외). pytest 는 `returncode` 뿐 아니라 요약도 본다 — `skipped`·`xfailed`·`xpassed`·`deselected` 가 0 이 아니면 실패다(ADR-040) |
| 의존성 취약점 0건 | `pip-audit --strict` — 설치된 의존성에 공개된 권고가 하나라도 있으면 실패(ADR-035) |
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
| `gate` | `uv sync --locked`(락이 `pyproject.toml` 과 어긋나면 실패) → ruff(lint·format) → mypy(콜드 캐시) → bandit(MEDIUM 이상, `app`·`main.py`·`config.py`) → `review_gate --fast`(위 표의 구조 검사·의존성 감사) → compose 의 `redis-test` 기동 → `pytest -m "not mysql" -rsxX --cov=app --cov-branch --cov-report=term-missing`(커버리지는 측정·출력만) → **skipped/xfailed/xpassed 가 있으면 실패** → `alembic heads` 단일 head 확인 |
| `mysql` | `uv sync --locked` → compose 의 `mysql-test` 기동 → `pytest -m mysql --mysql-required` → skip 또는 0건이면 실패 |

두 job 은 테스트 집합이 정확히 상보입니다. push 외에 매주 월요일 09:00(KST)에도 실행해, 코드 변경이 없는 주에 새로 공개된
의존성 권고를 잡습니다. 배포·이미지 빌드는 이 저장소 범위 밖입니다.
커밋 전 훅(`.pre-commit-config.yaml`)은 저장소가 추적하지 않는 로컬 선택 설정입니다 — 같은 검사는 CI 가 합니다.

커버리지 하한은 `pyproject.toml` 의 `[tool.coverage.report] fail_under` 하나가 정하고 **기본값은 0**(하한 없음)입니다 —
처음에는 기능이 제대로 동작하는지가 먼저라는 사용자 결정입니다. CI 는 수치를 출력만 합니다. 올리는 방법은
[DEVELOPMENT §12.3](./docs/guides/DEVELOPMENT.md#123-커버리지-하한).

---

## API

`app.openapi()` 로 확인한 전량 — **24 경로 / 39 오퍼레이션**. 모든 기능 API 는 `/api/v1/<기능명>/…`
형태이며, `tests/test_route_inventory.py` 가 경로·메서드를 고정합니다(새 라우트를 추가하면 그 테스트와
이 표를 함께 갱신). 요청·응답 형식은 `DEBUG=true` 의 `/docs` 에서 봅니다.

| 태그 | 메서드·경로 | 비고 |
|---|---|---|
| Health | `GET /health` · `GET /ready` | liveness / readiness(503) |
| Home | `GET /api/v1/home/access-logs` · `/recent` · `/by-ip/{ip_address}` · `/by-user/{user_id}` · `/stats` | 접속 로그 조회(전부 읽기 세션, 슈퍼유저 전용) |
| Blog | `GET·POST /api/v1/blog/posts` · `GET·PATCH·DELETE /api/v1/blog/posts/{post_id}` | CRUD |
| Reply | `GET·POST /api/v1/reply/replies` · `GET·PATCH·DELETE /api/v1/reply/replies/{reply_id}` | CRUD |
| SNS | `GET·POST /api/v1/sns/posts` · `GET·PATCH·DELETE /api/v1/sns/posts/{post_id}` | CRUD |
| User | `GET·POST /api/v1/user/users` · `GET·PATCH·DELETE /api/v1/user/users/{user_id}` | CRUD |
| Auth | `POST /api/v1/auth/register` · `POST /api/v1/auth/login`(form) · `POST /api/v1/auth/refresh` · `POST /api/v1/auth/logout` · `GET /api/v1/auth/me`(Bearer) | 인증 흐름은 아래, 상세는 [ARCHITECTURE §11](./docs/guides/ARCHITECTURE.md#11-인증-jwt) |
| Catalog | `GET·POST /api/v1/catalog/products` · `GET·PATCH·DELETE /api/v1/catalog/products/{product_id}` | ORM 참조 예제 |
| Reports | `GET /api/v1/reports/sales/daily` · `POST /api/v1/reports/sales/daily/snapshots` | Raw SQL 참조 예제(조회·적재) |

DELETE 와 `POST /auth/logout` 은 204(본문 없음)입니다. 오류 응답은 `{"error_code", "message", "detail"}` 형식입니다.
예외가 실은 헤더는 그대로 실립니다 — 405 `Allow`, 401 `WWW-Authenticate: Bearer`, 429 `Retry-After`.

인증 흐름 — `register` → `login`(form) 으로 `{access_token, refresh_token, token_type, expires_in}` 를 받고, API 는
`Authorization: Bearer <access_token>` 으로 부릅니다. access 가 만료되면 `refresh` 에 refresh 토큰을 보내 **새 쌍**을 받습니다 —
보낸 refresh 는 그 순간 못 쓰게 되고, 이미 쓴 refresh 가 다시 오면 탈취로 보고 그 계열(family) 전체를 폐기합니다(401).
`logout` 은 그 계열을 폐기합니다. 로그인·회원가입이 한도를 넘으면 429 와 `Retry-After`(초)가 옵니다.
access 토큰에는 사용자 ID(`sub`)·사용자명·슈퍼유저 여부(`su`)가 실려, 기능 API 는 DB 조회 없이 권한을 판정합니다.
토큰이 없거나 만료·위조됐으면 401(`WWW-Authenticate: Bearer`), 권한이 없으면 403(`FORBIDDEN`)입니다.

### 권한

모든 API 뷰는 경로 데코레이터의 `dependencies=[...]` 에 접근 수준을 **하나** 선언합니다 — `Public`(인증 없는 조회),
`PublicWrite`(인증 없는 쓰기를 명시적으로 연다), `LoginRequired`(401), `SuperuserRequired`(401/403). 사용자 정보가 필요한 뷰는
인자 `principal: CurrentPrincipal`/`SuperuserPrincipal` 로 같은 선언을 대신합니다. 선언이 없거나 모순된 뷰(수준 둘,
쓰기에 `Public`, 조회에 `PublicWrite`)가 하나라도 있으면 **서버가 기동하지 않습니다** — 위반 전체 목록과 함께
`AccessPolicyError` 로 멈춥니다(`app/core/security/access.py` 의 `AccessPolicyGuard`). 아래 표는 예시 기능의 정책이고,
`tests/test_authorization.py` 의 `EXPECTED_ACCESS` 가 라우트별로 고정합니다.

| 기능 | 조회 | 생성 | 수정 | 삭제 |
|---|---|---|---|---|
| Blog · SNS · Reply | 공개 | 로그인 — 작성자(`author`·`author_id`)는 서버가 토큰으로 채운다 | 작성자 또는 슈퍼유저 | 작성자 또는 슈퍼유저 |
| Catalog | 공개 | 슈퍼유저 | 슈퍼유저 | 슈퍼유저 |
| Reports | 슈퍼유저 | 슈퍼유저(스냅샷 적재) | — | — |
| Home(접속 로그) | 슈퍼유저 | — | — | — |
| User | 목록 슈퍼유저 · 단건 본인 또는 슈퍼유저 | 슈퍼유저(비밀번호 필수, `is_superuser` 지정 가능) | 본인 또는 슈퍼유저 — `is_active`·`is_superuser` 는 슈퍼유저만 | 슈퍼유저 |
| Auth | `me` 는 로그인 | `register`·`login`·`refresh`·`logout` 공개 쓰기(`PublicWrite` — 가입·로그인은 레이트 리밋) | — | — |
| Health(`/health`·`/ready`) | 공개 | — | — | — |

- 인가 도입 전에 만든 게시글·피드·댓글은 작성자 ID 가 비어 있어 **슈퍼유저만** 고칠 수 있습니다.
- 사용자를 비활성화(`is_active=false`)하거나 삭제하면 그 사용자의 refresh 토큰이 모두 폐기됩니다. 이미 발급된
  access 토큰은 만료(기본 15분)까지 유효합니다 — 권한 회수도 같습니다.
- `/admin`(SQLAdmin)은 이 표와 별개로 **활성 슈퍼유저 로그인**(서명 세션 쿠키 `admin_session`)으로만 들어갑니다.
  로그인한 슈퍼유저는 관리 화면에서 모든 모델을 조회·수정·삭제할 수 있습니다. 관리 세션은 API 를 인증하지 않고
  (API 는 Bearer 토큰만 본다), 강등·비활성화는 다음 관리 화면 요청부터 바로 막힙니다(요청마다 DB 확인).
  상세는 [관리 화면 인증 안내서](./docs/guides/admin-auth-guide.html).

### 첫 관리자 만들기

`POST /users` 는 슈퍼유저만 부를 수 있으므로 첫 슈퍼유저는 서버 밖 도구로 만듭니다(Django `createsuperuser` 와 같다).
DB 접속은 `.env` 설정을 그대로 쓰고, 마이그레이션이 먼저 적용돼 있어야 합니다.

```bash
uv run python -m scripts.create_superuser --username admin --email admin@example.com   # 비밀번호를 두 번 묻는다
# 자동화: 비밀번호를 표준 입력 한 줄로 (명령줄 인자로 넘기지 않는다 — 셸 기록·ps 에 남는다)
printf '%s\n' "$ADMIN_PASSWORD" | uv run python -m scripts.create_superuser --username admin --email admin@example.com --password-stdin
```

만든 계정은 관리 화면(`/admin/login`) 로그인 계정이기도 합니다.
이미 있는 사용자명이면 비밀번호·이메일은 그대로 두고 슈퍼유저로 **승격**합니다. 종료 코드는 0 성공, 1 입력 오류,
2 인자 오류입니다. 새 엔드포인트를 보호하는 방법은 [DEVELOPMENT §3.1](./docs/guides/DEVELOPMENT.md#31-라우트-보호--principal-주입)를 봅니다.

---

## 운영 배포 체크리스트

4·5번(그리고 남아 있는 예전 `ADMIN` 설정)은 **앱이 직접 기동을 거부**합니다(설정 검사, ADR-027·028·030·045,
admin-login ADR-005). 그 밖의 조합(`SERVER_HOST` 등)은 앱이 막지 않으므로 아래를 확인합니다. A~D 는 이번
버전에서 **배포 전에 반드시** 할 일입니다(관리 화면 인증 안내서의 [운영 절](./docs/guides/admin-auth-guide.html#ops)).

| # | 확인 | 빠뜨리면 |
|---|---|---|
| A | 프록시 뒤 배포면 `TRUSTED_PROXY_HOPS` 를 **앞단 프록시 단 수**로 설정했는가 | 0 이면 모든 클라이언트가 프록시 IP 하나로 보여 접속 로그와 로그인 레이트 리밋(API·`/admin`)이 전체 사용자를 한 사람으로 취급한다(한 명의 실패가 모두를 막는다). 실제보다 크게 잡으면 클라이언트가 IP 를 위조할 수 있다 |
| B | KST→UTC 시각 마이그레이션(리비전 `a7c9e1f3b5d6`) 전에 **백업**했고, 기존 MySQL 값이 +09:00 이 아니었다면 리비전의 `_LEGACY_OFFSET` 을 그 오프셋으로 바꿨는가 | 리비전은 기존 값을 모두 +09:00 으로 가정하고 UTC 로 고쳐 쓴다 — 다른 시간대였다면 모든 시각이 틀어지고 되돌릴 원본이 없다 |
| C | 첫 관리자를 `python -m scripts.create_superuser` 로 만들었는가(대화형 또는 `--password-stdin`) | 관리 경로 API 를 아무도 부를 수 없고(403), `/admin` 에 로그인할 계정도 없다 — 이 계정이 `/admin` 로그인 계정이다 |
| D | `/admin` 은 **활성 슈퍼유저 로그인**이 필요하다는 것을 알고, 그 세션 쿠키 서명 키 `SESSION_SECRET_KEY` 를 교체했는가. 관리 화면을 쓰지 않으면 `ADMIN_DISABLED=true` 인가 | 예시 키면 기동 거부. 키가 새면 세션 쿠키를 위조할 수 있다. 쓰지 않는 관리 화면을 켜 두면 로그인 화면이 공격 표면으로 남는다 |
| 1 | 예전 설정 `ADMIN`(·인증 없는 관리 화면 확인 플래그)을 환경 변수·`.env` 에서 지웠는가 | `ADMIN` 이 남아 있으면 기동 거부(뜻이 뒤집힌 이름이라 조용히 무시하지 않는다) |
| 2 | 외부 노출이 필요 없으면 `SERVER_HOST=127.0.0.1` 인가 (`python main.py` 실행 시) | 기본값 `0.0.0.0` |
| 3 | 관리 화면을 켰다면 HTTPS 로만 접속하는가(배포 환경 쿠키는 `Secure`), 가능하면 리버스 프록시·VPN 으로 `/admin` 접근 출처도 좁혔는가 | HTTP 로는 로그인이 유지되지 않는다. 출처 제한은 로그인 화면 자체를 숨기는 추가 방어선이다 |
| 4 | `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`(서로 다른 값)·`SESSION_SECRET_KEY`·`MYSQL_PASSWORD` 를 교체했는가 (쓰는 경우 `REDIS_PASSWORD`·`SMTP_PASSWORD` 도) | 예시 값·빈 값·32자 미만이면 test 외 모든 `ENV` 에서 기동 거부(`RuntimeError`, 이름만 표시) |
| 4-1 | `ENV=production`(또는 `staging`)을 **명시**했는가 | 기본값 `development` 로 뜨면 `DEBUG`·`LOG_LEVEL` 검사가 빠지고 관리 세션 쿠키에 `Secure` 가 붙지 않는다. `.env` 없이 환경 변수로 주입하는 배포는 `ENV` 가 없으면 기동 거부 |
| 5 | `DEBUG=false` 인가 | `/docs`·`/openapi.json` 공개, 500 응답에 예외 문자열 노출(DSN 비밀번호·`password=`·`Authorization` 형태만 `***` 로 가려진다), worker 마다 startup 에서 `create_all` 시도 |
| 6 | 스키마를 `alembic upgrade head` 로 먼저 적용했는가 | `DEBUG=false` 는 테이블을 만들지 않는다 |
| 7 | `CORS_ALLOW_ORIGINS` 를 실제 출처로 좁혔는가 | 기본값 `["*"]` |
| 8 | `LOG_SQL_ECHO_ENABLED=false` 인가 | SQL 바인딩 값(해시·토큰·검색어)이 로그 수집기로 나간다 |
| 9 | Redis(**6.2 이상**)가 준비됐고, 컨테이너 종료 유예 시간이 종료 예산보다 긴가 | Redis 가 없거나 6.2 미만이면 기동 실패 / 유예가 짧으면 정리 도중 SIGKILL ([ARCHITECTURE §8.2](./docs/guides/ARCHITECTURE.md#82-시간-예산)) |
| 10 | worker 수 × DB 풀 크기가 DB 최대 연결 수 안인가 | [ARCHITECTURE §4.1](./docs/guides/ARCHITECTURE.md#41-엔진과-커넥션-풀) |
| 11 | 접속 로그 보존 기간(`ACCESS_LOG_RETENTION_DAYS`, 기본 365일)을 정했고, Celery worker 와 **beat 한 개**를 띄웠는가 — `uv run python -m celery -A app.celery.app:celery_app worker --loglevel=INFO`, `uv run python -m celery -A app.celery.app:celery_app beat --loglevel=INFO` | beat 가 없으면 접속 로그가 영원히 쌓인다(IP·UA·`session_id`·Referer 원문). beat 를 둘 띄우면 삭제가 두 번 돈다(해는 없지만 부하) ([ARCHITECTURE §13](./docs/guides/ARCHITECTURE.md#13-celery)) |

관리 화면의 기본값은 "켜짐 + 슈퍼유저 로그인" 이고 `SERVER_HOST` 기본값은 `0.0.0.0` 이라, 아무것도 설정하지 않은
배포는 **로그인 화면이 네트워크에 열린** 상태입니다. 로그인한 슈퍼유저는 API 의 [권한](#권한) 표와 별개로 모든 모델을
고칠 수 있으므로 슈퍼유저 계정·`SESSION_SECRET_KEY` 가 곧 관리 화면의 열쇠입니다. refresh 토큰은 Redis 에 회전 기록이 남아
로그아웃·재사용 탐지로 폐기되지만, access 토큰은 폐기 목록이 없어 만료(`ACCESS_TOKEN_EXPIRE_MINUTES`, 기본 15분)까지
유효합니다 — 관리 세션은 반대로 요청마다 DB 를 확인해 강등·비활성화가 즉시 반영됩니다.

---

## 참고 자료

- [FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/) ·
  [Pydantic](https://docs.pydantic.dev/latest/) · [Alembic](https://alembic.sqlalchemy.org/)

## 라이선스

MIT License
