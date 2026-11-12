# FastAPI Default Project Structure

**표준 FastAPI 배선의 기준 구현체**입니다. 기능(feature)마다 `app/features/<name>/` 아래에
`api/routers/v1 → dependencies → services → repositories → models·schemas` 를 두고, 각 기능이 공개한
`router` 를 `main.py` 가 **명시적인 `include_router` 한 줄**로 취합합니다. 자동 탐색·데코레이터 등록·
UnitOfWork 같은 숨은 배선은 없습니다 — 무엇이 어디에 연결되는지는 `main.py` 와 각 기능의 `dependencies/`
만 읽으면 보입니다.

- 트랜잭션은 **쓰기 핸들러 본문**이 응답 DTO 검증 뒤 `await service.commit()` 한 번으로 닫고, 조회는 읽기
  전용 세션을 써서 커밋하지 않습니다.
- 데이터 접근 방식의 참조 예제가 둘 있습니다 — `catalog`(ORM Repository)와 `reports`(Raw SQL Repository).
  두 기능은 Repository 구현만 다르고 나머지 계층은 같습니다.
- 인증(JWT, OAuth2 password flow)·뷰 단위 접근 수준 선언·SQLAdmin 관리 화면·접속 로그·Celery·
  읽기/쓰기 DB 라우팅·큐 기반 로깅이 함께 들어 있습니다.

## 문서

| 문서 | 내용 |
|---|---|
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | 디렉터리 구조, 계층, DB 세션·라우팅, 인증·권한, 관리 화면, 미들웨어, 로깅, Celery, 수명주기 |
| [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) | 새 기능 추가, 테스트 구조·작성 규칙, 마이그레이션, 게이트·CI |

## 필요한 것

- Python 3.14(`.python-version`), [uv](https://docs.astral.sh/uv/)
- MySQL 8 — 앱 DB(`aiomysql`), Alembic(`pymysql`)
- Redis 6.2 이상 — **기동 필수**. 연결·버전 확인에 실패하면 서버가 뜨지 않습니다. 레이트 리밋·refresh 토큰
  회전·관리 세션·Celery broker 가 씁니다.

테스트는 외부 자원이 필요 없습니다(SQLite·fakeredis).

## 빠른 시작

```bash
uv sync
cp .env.example .env        # 아래 "설정" 의 값을 채운다
uv run uvicorn main:app --reload --port 8000
```

- `DEBUG=true`(기본)면 기동 시 **없는 테이블만** 만들고 `/docs`(Scalar)·`/openapi.json` 을 엽니다.
  운영(`DEBUG=false`)에서는 테이블을 만들지 않으니 먼저 `uv run alembic upgrade head` 를 실행합니다.
- `uv run python main.py` 도 같은 앱을 띄웁니다(`SERVER_HOST`·`SERVER_PORT`, `DEBUG` 면 reload).
- 확인: `GET /health`(프로세스 생존), `GET /ready`(DB `SELECT 1` 과 Redis `PING`, 실패하면 503).
- 첫 관리자: `uv run python -m scripts.create_superuser --username admin --email admin@example.com`
  (비밀번호는 대화형으로 두 번, 자동화는 `--password-stdin` 으로 표준 입력 한 줄). 이미 있는 사용자는
  슈퍼유저로 승격만 합니다. 이 계정이 슈퍼유저 전용 API 와 `/admin` 로그인 계정입니다.
- Celery(접속 로그 통계·보존 기간 삭제):
  `uv run python -m celery -A app.celery.app:celery_app worker --loglevel=INFO`,
  주기 작업은 beat 하나: `uv run python -m celery -A app.celery.app:celery_app beat --loglevel=INFO`.

## 설정

설정은 `config.py` 의 Pydantic Settings 가 환경 변수 → `.env` → 기본값 순으로 읽습니다. 전체 목록과 설명은
`.env.example` 에 있습니다. 설정 검사는 import 시점에 돌고, 위반이면 **기동을 멈춥니다**(`ENV=test` 는 검사하지
않습니다).

| 변수 | 규칙 |
|---|---|
| `ENV` | `development`·`staging`·`production`·`test`. 기본 `development` |
| `ACCESS_TOKEN_SECRET_KEY`, `REFRESH_TOKEN_SECRET_KEY`, `SESSION_SECRET_KEY` | 예시 값(`change-this…`·`your-…`·빈 값) 금지, 32자 이상, access 와 refresh 는 서로 달라야 함. 생성: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` | `MYSQL_PASSWORD` 는 예시 값·빈 값 금지 |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` | 비밀번호는 비워도 됨(인증 없는 Redis). 값이 있으면 예시 값 금지 |
| `DEBUG` | `staging`·`production` 에서는 `true` 금지. `LOG_LEVEL=DEBUG` 도 금지 |

- `.env` 파일이 없으면 `ENV`, 세 비밀 키, `MYSQL_HOST`·`MYSQL_USER`·`MYSQL_PASSWORD`·`MYSQL_DATABASE` 가
  환경 변수로 직접 와야 합니다(컨테이너 배포).
- 예전 설정 `ADMIN` 이 남아 있으면 기동을 멈춥니다 — 관리 화면을 끄는 설정은 `ADMIN_DISABLED=true` 입니다.
- 프록시 뒤 배포는 `TRUSTED_PROXY_HOPS` 를 앞단 프록시 단 수로 둡니다. 0(기본)이면 모든 클라이언트가
  프록시 IP 하나로 보여 접속 로그와 로그인 레이트 리밋이 전원을 한 사람으로 취급합니다.
- 접속 로그 보존: `ACCESS_LOG_RETENTION_DAYS`(기본 365, 0 이면 삭제 안 함) — beat 가 있어야 지워집니다.
- 이전 리비전 체인으로 만든 기존 DB 는 리비전이 baseline 하나로 합쳐져 예전 리비전 id 가 없습니다. 스키마가
  모델과 같은지 확인한 뒤 `uv run alembic stamp head` 로 맞춥니다.

## 테스트·검사

```bash
uv run python -m pytest                          # 전체 (pyproject 가 DEBUG=true, ENV=test 를 준다)
uv run ruff check . && uv run ruff format --check .
uv run mypy .
uv run python -m scripts.review_gate             # 위 전부 + pip-audit + 구조 검사
uv run python -m scripts.review_gate --fast      # pytest 제외 (CI 가 쓰는 형태)
```

`skipped`·`xfailed` 가 하나라도 있으면 CI 가 실패합니다. MySQL 테스트(`tests/mysql/`)는 CI 전용입니다 — 로컬에서
돌리려면 자기 소유의 빈 MySQL 을 `MYSQL_TEST_URL` 로 줍니다. 자세한 규칙은
[docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md).

## 라이선스

[LICENSE](./LICENSE)
