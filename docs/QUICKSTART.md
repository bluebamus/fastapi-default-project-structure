# QUICKSTART — 처음 보는 사용자를 위한 최소 실행 경로

이 저장소는 MySQL·Redis·Celery·SQLAdmin·JWT·rate limit·DB read/write 라우팅을 모두
포함한다. 전부 이해하고 시작할 필요는 없다. 이 문서는 **가장 먼저 무엇만 알면 되는지**만
다룬다. 전체 구조는 [ARCHITECTURE.md](./ARCHITECTURE.md), 전체 설정은 [../README.md](../README.md).

---

## 1단계 — 인프라 없이 30초 안에 확인

DB도 Redis도 없이 앱이 뜨는지부터 본다.

```bash
uv sync
DEBUG=false uv run uvicorn main:app --port 8000
```

```bash
curl http://127.0.0.1:8000/health
# {"status":"healthy","version":"0.1.0"}
```

여기까지는 **어떤 외부 서비스도 필요 없다**. 배선이 정상인지 확인하는 용도다.

### 이 상태에서 되는 것 / 안 되는 것

| | 동작 | 이유 |
|---|---|---|
| `GET /health` | ✅ | DB를 건드리지 않는다 |
| `GET /api/v1/blog/posts` 등 도메인 API | ❌ 500 | MySQL 연결이 필요하다 |
| `GET /docs` (Scalar), `/openapi.json` | ❌ 404 | **`DEBUG=false` 가 문서를 끈다** (운영 보안 기본값) |

> API 문서를 보려면 `DEBUG=true` 여야 하고, `DEBUG=true` 는 MySQL을 요구한다(2단계).
> 이 둘이 한 스위치에 묶여 있다는 점이 첫 실행에서 가장 헷갈리는 부분이다.

---

## 2단계 — 도메인 API까지 쓰려면 MySQL 하나

### 왜 필요한가

`DEBUG=true`(기본값)면 앱 시작 시 `create_db_tables()` 가 실행된다. 즉 **아무 설정 없이
`uvicorn main:app` 을 그냥 실행하면 MySQL이 없어서 startup 단계에서 실패한다.**

```text
[Startup] 데이터베이스 테이블 생성 실패: (pymysql.err.OperationalError)
(2003, "Can't connect to MySQL server on 'localhost'")
```

이 메시지를 봤다면 설정이 틀린 게 아니라 **DB가 없는 것**이다.

### MySQL 띄우기

```bash
docker run -d --name fastapi-mysql -p 3306:3306 \
  -e MYSQL_ALLOW_EMPTY_PASSWORD=yes \
  -e MYSQL_DATABASE=fastapi_db \
  mysql:8
```

기본 설정값(`MYSQL_HOST=localhost`, `MYSQL_USER=root`, `MYSQL_PASSWORD=""`,
`MYSQL_DATABASE=fastapi_db`)과 맞춘 것이라 `.env` 없이도 붙는다.

```bash
uv run uvicorn main:app --reload --port 8000
```

- API 문서: <http://127.0.0.1:8000/docs>
- 도메인 API: `GET /api/v1/blog/posts`

---

## 환경 변수 — 무엇이 필수인가

**필수는 없다.** 모든 설정에 기본값이 있어서 `.env` 없이도 기동한다.
처음에 의미 있는 것은 아래 정도이고, 나머지는 나중에 봐도 된다.

| 변수 | 기본값 | 첫 실행에서의 의미 |
|---|---|---|
| `DEBUG` | `true` | **가장 중요.** true=테이블 자동 생성 + `/docs` 켜짐(MySQL 필요) / false=둘 다 꺼짐(인프라 불필요) |
| `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | `localhost` / `root` / `""` / `fastapi_db` | 위 docker 명령과 맞춰져 있다 |
| `RATE_LIMIT_ENABLED` | — | 끄면 rate limit 데코레이터가 무동작 |
| `DB_ROUTER_ENABLED` | `false` | 기본은 단일 엔진. read/write 분리는 선택 기능 |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` | 로컬은 그대로 둬도 되지만 **배포 전 반드시 교체** |

전체 목록은 [`.env.example`](../.env.example).

`.env` 를 쓰려면:

```bash
cp .env.example .env
```

---

## 선택 기능 — 지금은 몰라도 된다

기본 실행 경로에 **필요 없는** 것들이다. 필요해질 때 해당 문서를 보면 된다.

| 기능 | 필요 인프라 | 언제 보면 되나 |
|---|---|---|
| Celery 비동기 태스크 | Redis | 백그라운드 작업이 필요해질 때 |
| SQLAdmin 관리자 화면 | (앱 내장) | 관리 UI가 필요할 때 |
| DB read/write 라우팅 | replica MySQL | 읽기 부하 분리가 필요할 때 |
| Alembic 마이그레이션 | MySQL | 운영 배포 시 (`DEBUG=false` 면 테이블 자동 생성이 꺼진다) |
| rate limit | (앱 내장) | 공개 API를 노출할 때 |

---

## 테스트 — 인프라 불필요

테스트는 in-memory SQLite를 쓰므로 MySQL 없이 그대로 돌아간다.

```bash
uv run pytest --basetemp .pytest_tmp
uv run ruff check .
uv run mypy . --cache-dir .mypy_tmp
```

---

## 새 도메인 추가

```bash
uv run python -m scripts.new_app orders --register
```

`--register` 가 `main.py` 의 import 와 `APPS` 목록까지 갱신한다(멱등 — 두 번 실행해도
중복되지 않는다). 모델 등록은 `app/core/db/models_registry.py` 가 디렉터리에서 자동
판별하므로 따로 손댈 곳이 없다.

`--register` 없이 만들었다면 `tests/test_domain_registration.py` 가 등록 누락을 잡아준다.

---

## 자주 막히는 지점

| 증상 | 원인 | 조치 |
|---|---|---|
| startup 에서 `Can't connect to MySQL server` | `DEBUG=true` 기본값이 테이블 생성을 시도 | MySQL을 띄우거나 `DEBUG=false` |
| `/docs` 가 404 | `DEBUG=false` 에서는 문서가 꺼진다 | `DEBUG=true` (MySQL 필요) |
| 도메인 API만 500 | 앱은 떴지만 DB가 없다 | 2단계 진행 |
| 새 도메인이 마운트 안 됨 | `main.py` 의 `APPS` 미등록 | `--register` 또는 수동 추가 |

---

## 검증 상태

이 문서의 명령 중 다음은 실제로 실행해 확인했다(2026-08-10 최초 확인, FastAPI 0.141.x, Python 3.14):

- `DEBUG=false` 기동 → `/health` 200, 도메인 API 500 — **확인**
- 기본값(`DEBUG=true`) + MySQL 없음 → startup 실패 — **확인**
- pytest / ruff / mypy — **확인**

MySQL `docker run` 이후 경로는 이 환경에 Docker가 없어 실행 확인하지 못했다. 설정
기본값과 대조해 작성했으므로, 다를 경우 이 문서를 고쳐 주기 바란다.
