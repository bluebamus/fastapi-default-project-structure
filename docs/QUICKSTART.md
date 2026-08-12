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
| `GET /api/v1/blog/posts` 등 기능 API | ❌ 500 | MySQL 연결이 필요하다 |
| `GET /docs` (Scalar), `/openapi.json` | ❌ 404 | **`DEBUG=false` 가 문서를 끈다** (운영 보안 기본값) |

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
| `RATE_LIMIT_ENABLED` | `true` | 켜져 있다. 끄면 rate limit 데코레이터가 무동작 |
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
| rate limit | (앱 내장) | **켜짐** (`100/minute`) | 회원가입·로그인에만 적용. 다른 라우트로 넓힐 때 |

---

## 테스트 — 인프라 불필요

테스트는 in-memory SQLite를 쓰므로 MySQL 없이 그대로 돌아간다.

```bash
uv run python -m pytest --basetemp .pytest_tmp
uv run ruff check .
uv run mypy . --cache-dir .mypy_tmp
```

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
from app.features import auth, blog, home, reply, sns, user, orders   # ← import 추가
app.include_router(orders.router, prefix="/api")                      # ← 취합 한 줄 추가
```

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

**최종 확인: 2026-08-12** (FastAPI 0.141.x, Python 3.14). 아래는 실제로 실행하거나
설정값을 읽어 대조한 결과다.

| 항목 | 방법 | 결과 |
|---|---|---|
| `DEBUG=false` 기동 → `/health` | 요청 | **200** `{"status":"healthy","version":"0.1.0"}` — 위 응답 예시와 일치 |
| `DEBUG=false` → `/docs` · `/openapi.json` | 요청 | **404** 둘 다 |
| 기본값(`DEBUG=true`) + MySQL 없음 → startup 실패 | 기동 | 확인 |
| 표의 기본값 전부 | `config.py` 필드 기본값 직접 읽기 | 일치 (`DEBUG`·`ADMIN`·MySQL 4종·`RATE_LIMIT_ENABLED`·`DB_ROUTER_ENABLED`·토큰 키 2종) |
| pytest / ruff / mypy | 실행 | 186 passed · 청정 · 146 files Success |

MySQL `docker run` 이후 경로는 이 환경에 Docker 가 없어 **실행 확인하지 못했다.** 설정
기본값과 대조해 작성했으므로, 다를 경우 이 문서를 고쳐 주기 바란다.
