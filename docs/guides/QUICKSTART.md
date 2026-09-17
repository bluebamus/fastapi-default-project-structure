# QUICKSTART — 처음 보는 사용자를 위한 최소 실행 경로

이 저장소는 MySQL·Redis·Celery·SQLAdmin·JWT·DB read/write 라우팅을 모두
포함한다. 전부 이해하고 시작할 필요는 없다. 이 문서는 **가장 먼저 무엇만 알면 되는지**만
다룬다. 전체 구조는 [ARCHITECTURE.md](./ARCHITECTURE.md), 전체 설정은 [../../README.md](../../README.md).
ORM 과 Raw SQL 을 각각 어떤 순서로 만드는지는
[ORM/Raw 워크플로우 개발 지침서](./ORM-RAW-WORKFLOW.md).

검토 기준: **2026-09-17 현재 작업 트리**. 설정부터 자원 해제까지는 [서버 수명 HTML 안내서](./server-lifecycle-guide.html),
신규 뷰·테이블 개발은 [개발 HTML 지침서](./feature-development-guide.html)를 함께 읽습니다.

---

## 1단계 — Redis를 준비해 최소 HTTP 배선 확인

MySQL 없이 앱 배선부터 확인할 수 있지만, startup 단계의 연결 검증을 통과하려면 Redis는 필요하다.

```bash
docker run --rm -d --name fastapi-redis -p 6379:6379 redis:7-alpine
uv sync
DEBUG=false uv run uvicorn main:app --port 8000
```

위 환경변수 지정은 Bash 문법입니다. PowerShell에서는 다음처럼 실행합니다.

```powershell
$env:DEBUG = "false"
uv run uvicorn main:app --port 8000
# 서버 종료 후 필요하면 개발 기본값으로 복원
Remove-Item Env:DEBUG
```

저장소 루트에서 실행합니다. `.env`가 있으면 MySQL·Redis 등의 값이 달라질 수 있고,
운영체제 환경변수는 `.env`보다 우선합니다. `.env.example`은 자동 fallback이 아닙니다.

```bash
curl http://127.0.0.1:8000/health
# {"status":"healthy","version":"0.1.0"}
```

앱은 시작하면서 `REDIS_HOST`/`REDIS_PORT`로 `ping()`을 호출하며, 연결되지 않으면 startup을
중단한다. 위 단계는 Redis만 사용해 HTTP 배선이 정상인지 확인하는 용도다.

### 이 상태에서 되는 것 / 안 되는 것

| | 동작 | 이유 |
|---|---|---|
| `GET /health` | ✅ | DB를 건드리지 않는다 |
| `GET /ready` | ❌ 503 | writer DB 에 `SELECT 1` 을 실제로 던진다 |
| `GET /api/v1/blog/posts` 등 기능 API | ❌ 500 | MySQL 연결이 필요하다 |
| `GET /docs` (Scalar), `/openapi.json` | ❌ 404 | **`DEBUG=false` 가 문서를 끈다** (운영 보안 기본값) |

> `/health` 와 `/ready` 는 일부러 다릅니다. `/health` 는 **프로세스 생존**만 봅니다 — 여기서
> DB 를 검사하면 DB 가 잠깐 흔들릴 때 멀쩡한 프로세스가 재시작됩니다. 트래픽을 보낼지
> 판단하는 쪽이 `/ready` 입니다. 오케스트레이터의 liveness probe 에는 `/health`,
> readiness probe 에는 `/ready` 를 연결하세요.

> API 문서를 보려면 `DEBUG=true` 여야 하고, `DEBUG=true` 는 MySQL을 요구한다(2단계).
> 이 둘이 한 스위치에 묶여 있다는 점이 첫 실행에서 가장 헷갈리는 부분이다.

---

## 2단계 — 기능 API까지 쓰려면 MySQL 추가

### 왜 필요한가

`DEBUG=true`(기본값)면 앱 시작 시 `create_db_tables()` 가 실행된다. 즉 **아무 설정 없이
`uvicorn main:app` 을 그냥 실행하면 Redis ping을 먼저 통과해야 하고, 그다음 MySQL이 없으면
테이블 생성 단계에서 실패한다.**

```text
[startup] 테이블 생성 단계의 연결 오류 예시 (표현은 드라이버·버전에 따라 다름)
(2003, "Can't connect to MySQL server on 'localhost'")
```

DB 서버 미기동뿐 아니라 호스트·포트·방화벽·인증 설정 문제도 확인한다.

### MySQL 띄우기

```bash
docker run -d --name fastapi-mysql -p 3306:3306 \
  -e MYSQL_ALLOW_EMPTY_PASSWORD=yes \
  -e MYSQL_DATABASE=fastapi_db \
  mysql:8
```

기본 설정값(`MYSQL_HOST=localhost`, `MYSQL_USER=root`, `MYSQL_PASSWORD=""`,
`MYSQL_DATABASE=fastapi_db`)에 맞춘 로컬 예시다. DB 준비 완료·접속 권한과 Redis 가용성도 확인한다.
빈 root 비밀번호는 로컬 전용이며 운영에 사용하지 않는다.

```bash
uv run uvicorn main:app --reload --port 8000
```

- API 문서: <http://127.0.0.1:8000/docs>
- 기능 API: `GET /api/v1/blog/posts`

---

## 환경 변수 — 무엇이 필수인가

설정 문자열은 모두 기본값이 있어 `.env` 없이도 읽히지만, 기본 주소의 Redis 서버는 반드시
접속 가능해야 한다. 처음에 의미 있는 것은 아래 정도이고, 나머지는 나중에 봐도 된다.

| 변수 | 기본값 | 첫 실행에서의 의미 |
|---|---|---|
| `DEBUG` | `true` | true=개발 테이블 생성 + `/docs` 켜짐 / false=둘 다 꺼짐. false여도 DB API·`/ready`·접속 로그 저장에는 MySQL 필요. Redis ping은 양쪽 모두 필수 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | `localhost` / `6379` / `0` | startup `ping()` 대상. 연결 실패 시 서버가 시작되지 않는다 |
| `ADMIN` | `true` | `/admin` 관리 화면이 **기본으로 켜진다**. ⚠️ **인증이 없다** — 아래 주의 참고 |
| `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | `localhost` / `root` / `""` / `fastapi_db` | 위 docker 명령과 맞춰져 있다 |
| `DB_ROUTER_ENABLED` | `false` | 기본은 단일 엔진. read/write 분리는 선택 기능 |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` | 로컬은 그대로 둬도 되지만 **배포 전 반드시 교체** |

> **⚠️ `ADMIN=true` 가 기본값이고 `/admin` 에는 인증이 없습니다.**
> 로컬 개발에서 바로 DB 를 들여다볼 수 있도록 한 **의도된 기본값**이지만, 그 말은
> 앱에 도달할 수 있는 누구나 사용자·게시글·접속로그를 조회·수정·삭제하고 CSV 로
> 내보낼 수 있다는 뜻입니다(비밀번호 해시만 제외). **운영·스테이징은 `ADMIN=false`**
> 를 명시하거나 리버스 프록시에서 `/admin` 을 막으세요.

주요 항목은 [`.env.example`](../../.env.example)에 있고 일부(`LOG_LEVEL`, `ALEMBIC_DATABASE_URL`,
replica 자격증명 등)는 주석으로만 들어 있다. 모든 필드와 코드 기본값은 `config.py` 또는
[서버 수명 HTML 안내서 부록](./server-lifecycle-guide.html#config-reference)을 본다.

`.env` 를 쓰려면:

```bash
cp .env.example .env
```

PowerShell: `Copy-Item -LiteralPath .env.example -Destination .env`.
기존 `.env`가 있으면 덮어쓰지 않고 필요한 항목만 확인한다.
`DEBUG=false`의 미지정 로그 레벨은 INFO이다. `LOG_LEVEL`·`LOG_CONSOLE_LEVEL` 명시값은
DEBUG보다 우선하므로 false여도 DEBUG 로그가 출력될 수 있다. 시작 로그의 `(DEBUG=%s)`는
현재 설정을 메시지에 표시할 뿐 출력 여부를 분기하지 않는다.

---

## 선택 기능 — 지금은 몰라도 된다

기본 실행 경로에 **필요 없는** 것들이다. 필요해질 때 해당 문서를 보면 된다.

| 기능 | 필요 인프라 | 기본 상태 | 언제 보면 되나 |
|---|---|---|---|
| Celery 비동기 태스크 | startup에서 확인한 Redis | 꺼짐(워커 미기동) | 백그라운드 작업이 필요해질 때 |
| DB read/write 라우팅 | replica MySQL | 꺼짐 | 읽기 부하 분리가 필요할 때 |
| Alembic 마이그레이션 | MySQL | — | 운영 배포 시 (`DEBUG=false` 면 테이블 자동 생성이 꺼진다) |
| SQLAdmin 관리자 화면 | (앱 내장) | **켜짐** | `/admin` 으로 바로 접근. 인증 없음(위 주의) |

---

## 테스트 — 인프라 불필요

단위 테스트는 in-memory SQLite와 가짜 Redis를 쓰므로 외부 인프라 없이 돌아간다.

```bash
uv run python -m pytest --basetemp .pytest_tmp
uv run ruff check .
uv run mypy . --cache-dir .mypy_tmp
```

MySQL 방언에 의존하는 몇 건(Raw SQL 집계, 마이그레이션 왕복)은 **MySQL 이 없으면 skip**
된다 — 실패가 아니다. 실제 uvicorn 프로세스를 띄워 종료 순서를 보는
`tests/integration/test_uvicorn_lifecycle.py` 3건도 **Redis(`REDIS_HOST`/`REDIS_PORT`)에
닿지 못하면 skip** 된다. 1단계의 Redis 컨테이너를 띄워 두면 함께 실행된다.
MySQL 테스트까지 돌리려면 전용 컨테이너를 띄운다.

```bash
docker compose -f compose.test.yaml up -d     # MySQL 8.4, 호스트 포트 3308
uv run python -m pytest -m mysql
docker compose -f compose.test.yaml down -v   # 정리
```

> 포트가 3306 이 아니라 **3308** 인 것은 의도적이다. 로컬에 이미 떠 있는 MySQL 을 건드리지
> 않기 위해서다. 데이터 디렉터리는 tmpfs 라 컨테이너를 내리면 아무것도 남지 않는다.
>
> 접속이 "Access denied" 로만 실패한다면 그 포트를 다른 프로세스가 선점했는지부터 본다
> (Windows: `Get-NetTCPConnection -LocalPort 3308`). IDE 의 포트 포워딩이 조용히 다른
> MySQL 로 연결을 돌려보내는 일이 실제로 있었다.
>
> WSL2 에서 Docker 를 쓴다면, 유휴 상태가 이어지면 WSL VM 이 내려가면서 컨테이너도 함께
> 멈춘다(`docker ps -a` 에 `Exited (0)`). 이때 테스트는 **실패가 아니라 skip** 으로 넘어가므로
> 결과 줄의 `skipped` 개수를 보지 않으면 눈치채기 어렵다. `up -d` 로 다시 올리면 된다.

> `pytest` 가 아니라 **`python -m pytest`** 를 쓴다. 콘솔 스크립트(`uv run pytest`)가
> 다른 인터프리터를 집어 import 가 어긋난 전례가 있어 이쪽을 표준으로 삼는다.
> CI(`.github/workflows/ci.yml`)도 같은 형태로 돌린다.
>
> `--cache-dir .mypy_tmp` 는 로컬 편의용이다. **게이트 판정용 mypy 는 캐시를 지우고**
> 돌린 결과만 유효하다 — 따뜻한 캐시가 통과로 잘못 기록된 전례가 있어 CI 는 캐시를
> 복원하지 않는다.

---

## 새 기능 추가

`app/features/<name>/` vertical slice 를 만든 뒤 `main.py` 에 두 줄을 추가한다:

```python
# main.py
# 신규 기능 예시 — orders 기능 패키지와 router를 먼저 구현한 뒤 등록
from app.features import auth, blog, catalog, home, reply, reports, sns, user, orders  # ← 추가
app.include_router(orders.router, prefix="/api")                                       # ← 추가
```

> 무엇을 만들지 감이 안 잡히면 **`app/features/catalog/` 를 그대로 베끼세요.** 한 기능이
> 가져야 할 파일이 전부 들어 있는 최소 완결 예제입니다(ORM). 집계·리포트처럼 SQL 을 직접
> 써야 하면 `app/features/reports/` 쪽이 짝이 되는 예제입니다(Raw SQL).

모델 등록은 `app/core/db/models_registry.py` 가 `app/features/<name>/models/models.py` 를
디렉터리 스캔으로 자동 판별하므로 따로 손댈 곳이 없다(기능 `__init__.py` 에서 models import).
등록 누락은 `tests/test_router_registration.py` 가 잡아준다.

---

## 자주 막히는 지점

| 증상 | 원인 | 조치 |
|---|---|---|
| startup 에서 `Redis 연결 실패` | Redis 미기동·주소/포트/인증 오류 | `REDIS_*` 설정과 서버 가용성 확인. `DEBUG=false`로 우회되지 않음 |
| startup 에서 `Can't connect to MySQL server` | `DEBUG=true` 기본값이 테이블 생성을 시도 | MySQL을 띄우거나 `DEBUG=false` |
| `/docs` 가 404 | `DEBUG=false` 에서는 문서가 꺼진다 | `DEBUG=true` (MySQL 필요) |
| 기능 API만 500 | 앱은 떴지만 DB가 없다 | 2단계 진행 |
| 새 기능이 마운트 안 됨 | `main.py` 에 `include_router` 미등록 | import + `app.include_router(<name>.router, prefix="/api")` 추가 |

---

## 과거 실행 기록과 현재 검토 범위

**2026-09-17:** 현재 코드·설정·문서 연결을 검토했다. 같은 날 Redis·MySQL 없이
`uv run python -m pytest -q -rsxX`를 실행한 결과는 **407 passed · 3 skipped · 8 errors**였다.
skip 3건은 Redis 미기동으로 건너뛴 `test_uvicorn_lifecycle.py`, error 8건은 `-m mysql`
통합 테스트가 3308 포트에서 compose 컨테이너가 아닌 다른 MySQL을 만나 `Access denied`로
실패한 것이다(위 테스트 절의 포트 선점 주의 참고). `ruff check`·`mypy`는 청정,
`alembic heads`는 단일 head(`e5f7a9b1c4d5`)였다. 실제 서버·MySQL·Redis 성공 연결 검증은
새로 수행하지 않았다.

아래 실행 수치와 HTTP 결과는 **Redis 필수 startup 검증 도입 전의 과거 기록**이며 현재
테스트 수나 Redis 없이 기동할 수 있다는 근거가 아니다.

**과거 확인: 2026-08-13** (FastAPI 0.141.x, Python 3.14). 아래는 당시 실제로 실행하거나
설정값을 읽어 대조한 결과다.

| 항목 | 방법 | 결과 |
|---|---|---|
| `DEBUG=false` 기동 → `/health` | 요청 | **200** `{"status":"healthy","version":"0.1.0"}` — 위 응답 예시와 일치 |
| `DEBUG=false` → `/docs` · `/openapi.json` | 요청 | **404** 둘 다 |
| `DEBUG=false` + MySQL 없음 → `/ready` | 요청 | **503** (writer DB 확인 실패) |
| 기본값(`DEBUG=true`) + MySQL 없음 → startup 실패 | 기동 | 확인 |
| 표의 기본값 전부 | `config.py` 필드 기본값 직접 읽기 | 일치 (`DEBUG`·`ADMIN`·MySQL 4종·`DB_ROUTER_ENABLED`·토큰 키 2종) |
| pytest / ruff / mypy | 실행 | **373 passed** · 청정 · 187 files Success |
| MySQL 8.4 통합 경로 | `compose.test.yaml` 로 컨테이너 기동 후 `-m mysql` 실행 | 6건 통과 (Raw SQL 집계·경계값·정밀도·injection 방어, 마이그레이션 head→base→head 왕복) |

2단계의 `docker run` 명령(단일 MySQL, 포트 3306)은 이 환경에서 **실행 확인하지 않았다** —
통합 테스트용 `compose.test.yaml`(포트 3308) 경로만 검증했다. 설정 기본값과 대조해 작성했으므로,
다를 경우 이 문서를 고쳐 주기 바란다.
