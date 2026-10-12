# Charter — service-hardening  (Charter v0.1 / 2026-10-12)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순될 수 없다.
> 단계 B 이후의 "신규" 경로는 계획이다 — 단계를 진행하며 실제 경로로 확정하고 버전을 올린다.

## 1. 인벤토리 (Scope Inventory)

| 단계 | 경로 | 종류 | 비고 |
|---|---|---|---|
| A1 | `.github/workflows/ci.yml` | 설정 | `uv sync --locked` (gate·mysql job) |
| A1 | `scripts/review_gate.py`, `tests/scripts/` | 소스+테스트 | 파일 목록 = `git ls-files -z` (git 없으면 rglob) |
| A1 | `tests/test_ci_contract.py` | 테스트 | **신규** — ci.yml 계약 |
| A2 | `config.py` | 소스 | `URL.create` DSN·`REDIS_URL` 인코딩·`mask_dsn` 제거 |
| A2 | `migrations/env.py`, `app/core/db/session.py`, `app/core/resources.py`, `app/celery/app.py` | 소스 | URL 소비처 |
| A2 | `tests/core/test_db_router.py`, `tests/core/test_dsn.py` | 테스트 | 의미 비교로 전환 + **신규** 왕복 테스트 |
| A3 | `app/core/db/router.py` | 소스 | ORM 잠금 읽기 판정 |
| A3 | `app/core/repositories/repository_base.py`, `app/features/catalog/repositories/product_repository.py`, `app/features/home/repositories/user_access_log_repository.py` | 소스 | 기본 정렬·보조 키 |
| A3 | `tests/core/test_db_router.py`, `tests/core/test_read_only_guard.py`, `tests/core/test_repository_base.py` | 테스트 | 라우터 on/off·정렬 결정성 |
| B | `app/core/middlewares/` (신규 `client_ip.py`), `app/features/home/`, `app/core/repositories/repository_base.py`, `app/core/exception.py`, `app/features/*/schemas/`, `app/features/reports/`, `main.py`, `config.py` | 소스+테스트 | IP 결정·접속 로그·길이 절단·null PATCH·오류 매핑·날짜 상한 |
| C | `tests/` 공용 헬퍼(신규), `app/features/*/tests/`, `tests/integration/` | 테스트 | 세션 헬퍼·MySQL ORM 스모크 |
| D | `app/core/models/models_base.py`, `config.py`, `migrations/versions/`(신규 리비전), `app/features/reports/`, `app/celery/app.py` | 소스 | UTC 저장 |
| E | `app/core/resources.py`, `main.py`, `app/core/` (신규 Redis provider), `app/celery/`, `app/features/*/tasks.py`(신규), `compose.test.yaml` | 소스+설정 | Redis provider·`/ready`·태스크 발견 |
| F1 | `app/core/security/`(신규), `app/features/auth/`, `config.py`, `pyproject.toml`, `uv.lock` | 소스+설정 | 해시·토큰·회전 저장소·레이트 리밋 |
| F2 | `app/core/security/`, `app/features/{user,blog,sns,reply,catalog,reports,home}/`, `migrations/versions/`(신규 리비전 2), `scripts/create_superuser.py`(신규), `docs/crp/groups/orm-raw-repository/baseline/openapi.json` | 소스+문서 | Principal·소유권·인가·운영 도구 |
| 공통 | `README.md`, `docs/guides/ARCHITECTURE.md`, `docs/guides/DEVELOPMENT.md`, `.env.example` | 문서 | 각 단계가 바꾼 사실만 갱신 |

기준선 실측 (2026-10-12, 커밋 `eb70fbf`):

- 추적 `.py` 274개 · 테스트 파일 61개 · `pytest -m "not mysql"` 652 수집(641 passed · 3 skipped · 8 deselected)
  — skip 3건은 로컬에 Redis 가 없어 uvicorn 수명주기 테스트가 빠진 것이다(CI 는 compose 로 띄운다).

## 2. 계약 (Contract)

### 2-1. 지원 구성

- `orm-raw-repository` charter §2-1 과 같다(Python 3.14 · FastAPI · SQLAlchemy 2.x async · aiomysql/aiosqlite).
- Redis 는 필수(단계 E 이후 `/ready` 판정 대상). 인증은 OAuth2 password + Bearer JWT(F1·F2).
- 프록시 뒤 배포는 `TRUSTED_PROXY_HOPS` 로 홉 수를 명시한다(B).

### 2-2. 위협 모델

- 방어한다:
  - **크리덴셜 스터핑·무차별 대입** — 로그인·가입 레이트 리밋(ip+username, ip), 429 + `Retry-After` (F1)
  - **refresh 토큰 탈취** — 회전 + 재사용 탐지 시 family 폐기, 로그아웃·비활성화 시 폐기 (F1·F2)
  - **IDOR** — 소유권 정책(소유자 또는 슈퍼유저), 관리 경로는 슈퍼유저 (F2)
  - **헤더 위조** — 신뢰 홉 수 밖의 `X-Forwarded-For`·`X-Real-IP` 를 무시 (B)
  - **로그 유출** — DSN 비밀번호 마스킹(A2), 쿼리스트링 민감 값 마스킹(B), 오류 응답·로그에 원문·SQL 없음(B)
  - **토큰 혼동** — `type`·`iss`·`aud`·필수 claim 검증, 알고리즘 고정 (F1)
  - **CI 재현성 붕괴** — 락 불일치에서 실패(A1)
- 방어하지 않는다(비목표, §2-4):
  - SQLAdmin 무인증(설계상 유지 — C-9, residual-risk R-001), access 토큰 즉시 폐기(짧은 만료로 대신),
    분산 공격(IP 다수)에 대한 레이트 리밋 우회, 프록시 설정 오류로 인한 IP 위조(운영 책임)

### 2-3. 불변식 (Invariants)

- **INV-1**: DSN 은 문자열 조립 없이 `URL` 로만 만들고, 어떤 비밀번호든 `make_url` 왕복이 보존된다. (A2)
- **INV-2**: 잠금 읽기(text·ORM 모두)는 writer 로 가고 read-only 세션에서 거부된다. (A3)
- **INV-3**: 범용 목록과 시각 정렬 쿼리는 결정적 정렬(보조 키 PK)을 가진다. (A3)
- **INV-4**: 접속 로그는 500 을 포함한 모든 요청을 기록하고, 민감 쿼리 값·길이 초과 값이 그대로 저장되지 않는다. (B)
- **INV-5**: DB 시각은 UTC 로 저장되고 응답은 오프셋을 가진다. (D)
- **INV-6**: refresh 토큰은 한 번만 쓸 수 있고, 재사용은 그 family 전체를 폐기한다. (F1)
- **INV-7**: 보호 경로는 토큰 없이 401, 권한 없이 403 이며 인증은 주입으로만 이뤄진다. (F2)

### 2-4. 비목표 (Non-goals)

- SQLAdmin 인증 백엔드, OAuth 소셜 로그인, 이메일 인증·비밀번호 재설정 메일, 2FA, access 토큰 즉시 폐기,
  다중 테넌시, RBAC 세분화(슈퍼유저/일반 2단계만). 이 목록의 시나리오에서의 실패는 결함이 아니다.

## 3. 인수 기준 (Acceptance Criteria) — 단계마다 전부 그린

- [ ] **공통 게이트** — `uv run ruff check .` · `uv run ruff format --check .` · `uv run python -m mypy .` ·
      `pytest -m "not mysql"`(CI 마커식) skipped·xfailed 0 · `scripts/review_gate.py --fast` 의 구조 검사
- [x] **A** — `tests/test_ci_contract.py`(ci.yml 에 `--frozen` 없음·`uv sync --locked` 있음), 게이트 파일 목록이
      추적 파일만 담는 테스트, DSN 특수문자·IPv6·Alembic `%`·Redis URL 왕복, 잠금 읽기 라우터 on/off, 목록 정렬 결정성·offset 페이지 비중첩
- [ ] **B** — IP 결정(hops 0/N·위조·잘못된 값), 500 기록, 쿼리 마스킹, 컬럼 길이 절단, null PATCH 422, 오류 코드별 상태, 날짜 상한 422
- [ ] **C** — 헬퍼의 read-only 세션에서 flush 거부, MySQL ORM 스모크(`mysql` 마커, CI 실행)
- [ ] **D** — TypeDecorator bind/result/naive 거부, SQLite 마이크로초 보존, 응답 오프셋, MySQL 왕복·자정 경계(`mysql` 마커)
- [ ] **E** — `/ready` Redis 실패 503, `get_redis` provider, 태스크 자동 발견 목록, 기능 제거 시 include 무사
- [ ] **F1** — 해시·레거시 bcrypt 이전, 토큰 claim·만료·aud/iss·필수 claim·type 혼동, 회전·재사용 탐지·logout, 429+Retry-After·창 만료·성공 시 초기화, 엔드포인트 흐름
- [ ] **F2** — 401(없음/만료/위조), 403(타인·일반 사용자의 관리 경로), 소유자 수정, 슈퍼유저 우회, 비활성화 시 refresh 실패, 접속 로그 user_id, create_superuser
- [ ] 새 테스트마다 fail-on-revert 결과를 run-log 에 적는다(수정 전 코드에서 실패하는지)

## 4. 변경 이력

- v0.1 (2026-10-12): 최초 작성.
