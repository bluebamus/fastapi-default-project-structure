# QUICKSTART — 처음 보는 사용자를 위한 최소 실행 경로

이 저장소는 MySQL·Redis·Celery·SQLAdmin·JWT·DB read/write 라우팅을 모두
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

## 2단계 — 기능 API까지 쓰려면 MySQL 하나

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
- 기능 API: `GET /api/v1/blog/posts`

---

## 환경 변수 — 무엇이 필수인가

**필수는 없다.** 모든 설정에 기본값이 있어서 `.env` 없이도 기동한다.
처음에 의미 있는 것은 아래 정도이고, 나머지는 나중에 봐도 된다.

| 변수 | 기본값 | 첫 실행에서의 의미 |
|---|---|---|
| `DEBUG` | `true` | **가장 중요.** true=테이블 자동 생성 + `/docs` 켜짐(MySQL 필요) / false=둘 다 꺼짐(인프라 불필요) |
| `ADMIN` | `true` | `/admin` 관리 화면이 **기본으로 켜진다**. ⚠️ **인증이 없다** — 아래 주의 참고 |
| `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | `localhost` / `root` / `""` / `fastapi_db` | 위 docker 명령과 맞춰져 있다 |
| `DB_ROUTER_ENABLED` | `false` | 기본은 단일 엔진. read/write 분리는 선택 기능 |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` | 로컬은 그대로 둬도 되지만 **배포 전 반드시 교체** |

> **⚠️ `ADMIN=true` 가 기본값이고 `/admin` 에는 인증이 없습니다.**
> 로컬 개발에서 바로 DB 를 들여다볼 수 있도록 한 **의도된 기본값**이지만, 그 말은
> 앱에 도달할 수 있는 누구나 사용자·게시글·접속로그를 조회·수정·삭제하고 CSV 로
> 내보낼 수 있다는 뜻입니다(비밀번호 해시만 제외). **운영·스테이징은 `ADMIN=false`**
> 를 명시하거나 리버스 프록시에서 `/admin` 을 막으세요.

전체 목록은 [`.env.example`](../.env.example).

`.env` 를 쓰려면:

```bash
cp .env.example .env
```

---

## 선택 기능 — 지금은 몰라도 된다

기본 실행 경로에 **필요 없는** 것들이다. 필요해질 때 해당 문서를 보면 된다.

| 기능 | 필요 인프라 | 기본 상태 | 언제 보면 되나 |
|---|---|---|---|
| Celery 비동기 태스크 | Redis | 꺼짐(워커 미기동) | 백그라운드 작업이 필요해질 때 |
| DB read/write 라우팅 | replica MySQL | 꺼짐 | 읽기 부하 분리가 필요할 때 |
| Alembic 마이그레이션 | MySQL | — | 운영 배포 시 (`DEBUG=false` 면 테이블 자동 생성이 꺼진다) |
| SQLAdmin 관리자 화면 | (앱 내장) | **켜짐** | `/admin` 으로 바로 접근. 인증 없음(위 주의) |

---

## 테스트 — 인프라 불필요

테스트는 in-memory SQLite를 쓰므로 MySQL 없이 그대로 돌아간다.

```bash
uv run python -m pytest --basetemp .pytest_tmp
uv run ruff check .
uv run mypy . --cache-dir .mypy_tmp
```

MySQL 방언에 의존하는 몇 건(Raw SQL 집계, 마이그레이션 왕복)은 **MySQL 이 없으면 skip**
된다 — 실패가 아니다. 그것까지 돌리려면 전용 컨테이너를 띄운다.

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
| startup 에서 `Can't connect to MySQL server` | `DEBUG=true` 기본값이 테이블 생성을 시도 | MySQL을 띄우거나 `DEBUG=false` |
| `/docs` 가 404 | `DEBUG=false` 에서는 문서가 꺼진다 | `DEBUG=true` (MySQL 필요) |
| 기능 API만 500 | 앱은 떴지만 DB가 없다 | 2단계 진행 |
| 새 기능이 마운트 안 됨 | `main.py` 에 `include_router` 미등록 | import + `app.include_router(<name>.router, prefix="/api")` 추가 |

---

## 검증 상태

**최종 확인: 2026-08-13** (FastAPI 0.141.x, Python 3.14). 아래는 실제로 실행하거나
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
