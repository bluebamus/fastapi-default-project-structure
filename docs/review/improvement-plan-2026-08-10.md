# fastapi-default-project-structure 개선 작업 계획

작성일: 2026-08-10
근거 문서: [audit-report-2026-08-10.md](./audit-report-2026-08-10.md) (검수 보고서)
대상 저장소: 이 저장소 (`fastapi-default-project-structure`)

## 실행 결과 (2026-08-10)

브랜치 `worktree-plan-p1-p2` 에 항목별 커밋으로 완료.

| 항목 | 상태 | 비고 |
|---|---|---|
| P1-1 mypy 오류 | ✅ 완료 | `1 error` → `Success` (149 files) |
| P1-2 트랜잭션 경계 테스트 | ✅ 완료 | 4케이스 중 3 통과, 1 xfail(아래) |
| P1-3 명시적 트랜잭션 컨텍스트 | ⛔ 미착수(정상) | 조건 미충족 — 커밋 실패가 응답보다 먼저 발생함을 실측 확인 |
| P2-1 모델 import SSOT | ✅ 완료 | 중복이 2곳이 아니라 **3곳**이었음 |
| P2-2 `--register` | ✅ 완료 | 실제 `main.py` 대상 멱등성 확인 |
| P2-3 등록 누락 테스트 | ✅ 완료 | 미등록 도메인으로 실패 재현 후 확인 |
| P3-1 QUICKSTART | ✅ 완료 | 실측 기반 |
| P3-2 프로필 분리 | ⏸ 보류(계획대로) | 사용자 피드백 반복 시 재검토 |
| P4-1 읽기 경로 무커밋 | ✅ 완료 | 조회 13개 전환, xfail 해소 |
| P4-2 Alembic 체인 복구 | ✅ 완료 | 빈 DB `upgrade head` 성공 |
| P4-3 auth 읽기 세션 정리 | ✅ 완료 | 조회 라우트 14개 전부 읽기 전용 세션 |
| P5 FastAPI 상향 검토 | ⛔ 상향 보류 | 실측 결과 P1-3 이 **필수**가 됨 (아래 P5 절) |

게이트: `pytest 198 passed` (기준 177, xfail 0) · `ruff` 통과 · `mypy` 통과

### 계획과 달랐던 점 (3건)

1. **읽기 경로가 커밋한다** — P1-2 의 1번 케이스는 통과할 것으로 봤으나 실패했다.
   `strict xfail` 로 고정했다가 **P4-1 로 해소**하고 마커를 제거했다.

2. **Alembic 마이그레이션 체인이 불완전하다** (이번 작업과 무관한 기존 결함) —
   **P4-2 로 해소**.

3. **모델 import 중복이 3곳** — 계획서는 2곳으로 봤으나
   `tests/core/test_alembic_metadata.py` 에도 같은 목록이 있었다. 함께 통합했다.

### P4 실행 중 추가로 드러난 것

- **`home` 도 대상이었다.** 최초 보고에서는 `blog`/`reply`/`sns`/`user` 4개로 봤으나,
  `home` 은 엔드포인트 5개가 **전부 GET** 이고 모두 커밋하고 있었다. 가장 큰
  단일 기여였다. 쓰기가 없어 커밋 버전이 죽은 코드가 되므로 병렬 추가가 아니라
  기존 의존성을 전환했다.
- **테스트 픽스처 5개가 읽기 경로를 실제 MySQL 로 흘려보내고 있었다.** 라우트를
  `get_read_session` 으로 바꾸자 16개가 실패해 드러났다. 오버라이드를 추가해 해결.

## 0. 이 계획의 범위

검수 보고서의 P1/P2/P3 개선안을 실행 가능한 작업 단위로 분해한다.
각 작업은 **대상 파일 / 변경 내용 / 완료 조건(테스트)** 을 명시한다.

계획 수립 전 저장소 실측으로 확인한 사실:

| 보고서 주장 | 실측 결과 |
|---|---|
| `main.py:261` mypy 타입 오류 | 확인 — `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)` |
| 모델 import 목록 중복 | 확인 — `migrations/env.py:19-23`, `app/core/db/session.py:227-231` (동일 5개 도메인) |
| `new_app.py`에 `--register` 없음 | 확인 — 인자는 `name`, `--category`, `--with-admin` 뿐 |
| 트랜잭션 경계 테스트 부재 | **부분 부정** — `app/domains/auth/tests/test_transaction_boundary.py`에 읽기 경로 1건 존재. 쓰기 경로가 없음 |
| 도메인 등록 지점 | `main.py:33 APPS`, `migrations/env.py`, `session.py:create_db_tables()`, 각 도메인 `__init__.py` = 4곳 |

> 참고: `auth` 도메인은 모델이 없으므로 두 import 목록에서 빠진 것이 정상이다. SSOT 통합 시 "모델 없는 도메인"을 허용해야 한다.

---

## P1 — 게이트 차단 요인 (선행)

### P1-1. mypy `main.py:261` 타입 오류 해소

- **대상**: `main.py`
- **원인**: `slowapi._rate_limit_exceeded_handler`의 시그니처가 Starlette `add_exception_handler()` 기대 타입과 정적으로 불일치. `pyproject.toml`의 `slowapi.*` override는 `ignore_missing_imports`만 켜므로 arg-type 오류에는 무효.
- **작업**: 핸들러를 Starlette 시그니처(`Request, Exception -> Response`)에 맞춘 얇은 래퍼로 감싼다. 래퍼 안에서 `RateLimitExceeded`로 좁힌 뒤 원 핸들러에 위임한다.
  - `cast()` 단독 사용은 지양 — 타입만 속이고 런타임 계약은 검증하지 않는다.
- **완료 조건**:
  - `python -m mypy . --cache-dir .mypy_tmp` → `Success: no issues found`
  - `tests/test_rate_limit.py` 기존 통과 유지 (429 응답 형태 불변)

### P1-2. `yield` dependency 커밋 시점 검증 테스트 보강

- **대상**: `app/domains/<name>/tests/test_transaction_boundary.py` (auth 기존 파일 확장 + 쓰기 도메인 1곳 신규)
- **배경**: 현재 구조는 `get_<name>_service` 의존성이 `yield` 이후 `session.commit()`을 호출한다. FastAPI 상위 버전에서 `yield` 이후 코드의 실행 시점 / `Depends(scope=...)` 도입 시 이 경계가 바뀔 수 있다. 현재 핀: `fastapi (>=0.115.11,<0.116.0)`.
- **작업**: 다음 3가지를 커밋 카운팅 fixture로 고정한다.
  1. 읽기 전용 경로에서 `commit()`이 호출되지 않는다 *(auth에 이미 존재 — 다른 도메인으로 확장)*
  2. 쓰기 경로 성공 시 `commit()`이 정확히 1회 호출된다
  3. 라우터에서 예외 발생 시 `commit()` 없이 `rollback()`으로 종료된다
  4. **커밋 실패가 응답 바디 전송 이전에 발생한다** — commit에서 예외를 주입했을 때 클라이언트가 2xx가 아닌 5xx를 받는지 확인. 이것이 업그레이드 시 가장 먼저 깨질 지점이다.
- **완료 조건**: 위 4개 케이스가 현재 FastAPI 핀에서 통과. 실패 시 P1-3으로 승격.

### P1-3. (조건부) 명시적 트랜잭션 컨텍스트 전환

P1-2의 4번이 실패하면 — 즉 커밋 실패가 응답 전송 후에 일어나 데이터 불일치가 가능하면 — 쓰기 endpoint의 커밋을 의존성 teardown에서 라우터 내부 `async with session.begin()` 컨텍스트로 옮긴다.

**P1-2 결과를 보기 전에는 착수하지 않는다.** 결과가 정상이면 이 항목은 폐기하고 `docs/ARCHITECTURE.md`에 "업그레이드 시 재확인" 항목으로만 남긴다.

---

## P2 — 구조적 취약점 (중기)

### P2-1. 모델 import 목록 SSOT 통합

- **대상**: `app/core/db/session.py`, `migrations/env.py`, (신규) `app/core/db/models_registry.py`
- **현 상태**: 동일한 5줄짜리 import 목록이 두 파일에 복제되어 있다. 신규 도메인 추가 시 한쪽만 고치면 Alembic autogenerate 또는 DEBUG 테이블 생성 중 하나가 조용히 누락된다.
- **작업**: `app/domains/` 하위를 순회하며 `<domain>/models/models.py`가 존재하면 import하는 함수 하나(`import_all_models()`)를 만들고, 두 곳 모두 이 함수를 호출하도록 교체한다. 모델이 없는 도메인(`auth`)은 건너뛴다.
- **완료 조건**:
  - `Base.metadata.tables` 키 집합이 변경 전후 동일
  - `alembic revision --autogenerate` 결과가 비어 있음 (드리프트 없음)
  - P2-3 테스트가 이 함수를 기준으로 검증

### P2-2. `scripts/new_app.py --register` 옵션 추가

- **대상**: `scripts/new_app.py`, `tests/scripts/`
- **작업**: `--register` 플래그를 추가해 스캐폴딩 후 `main.py`의 import 라인과 `APPS` 리스트까지 자동 갱신한다.
  - P2-1을 먼저 적용하면 `migrations/env.py`와 `session.py`는 손댈 필요가 없어진다 → **P2-1 이후에 착수한다.**
  - 텍스트 치환 대상은 `main.py` 한 곳으로 축소. `APPS = [...]` 한 줄과 `from app.domains import ...` 한 줄만 편집.
  - 이미 등록된 이름이면 멱등하게 no-op.
- **완료 조건**: 임시 디렉터리에 앱을 스캐폴딩한 뒤 `--register`를 적용하면 `APPS`에 이름이 1회만 추가되고, 두 번 실행해도 중복되지 않는다.

### P2-3. 도메인 등록 누락 탐지 테스트

- **대상**: `tests/test_route_inventory.py` 또는 신규 `tests/test_domain_registration.py`
- **작업**: `app/domains/` 디렉터리 목록을 진실의 원천으로 삼아 다음을 대조한다.
  - 모든 도메인 패키지가 `main.py`의 `APPS`에 존재하는가
  - `models/models.py`를 가진 모든 도메인이 `Base.metadata`에 반영되었는가 (P2-1의 함수 경유)
  - 의도적으로 제외할 도메인은 테스트 내 명시적 allowlist로만 허용 (조용한 누락과 의도적 제외를 구분)
- **완료 조건**: 새 도메인 디렉터리를 만들고 등록을 생략하면 이 테스트가 실패한다.

---

## P3 — 포지셔닝 정리 (장기, 선택)

> 이 단계는 저장소의 **정체성 결정**이 선행되어야 한다. "범용 기본 템플릿"인지 "실무형 프로덕션 스타터"인지 확정하기 전에는 착수하지 않는다.

### P3-1. 진입 경로 문서 추가 (저비용, 먼저)

- **대상**: `README.md` 또는 신규 `docs/QUICKSTART.md`
- **작업**: MySQL/Redis/Celery 없이 앱을 띄우고 첫 엔드포인트를 호출하는 최소 경로를 문서화한다. 어떤 환경 변수가 필수이고 어떤 것이 선택인지 표로 구분.
- **근거**: 문서 분량 문제이지 구조 문제가 아니므로 코드 변경 없이 검수 보고서의 "기본 사용자 진입 장벽" 지적 대부분을 해소한다.

### P3-2. (조건부) 템플릿 프로필 분리

`minimal` / `api-db` / `production` 3종 분리는 **저장소 분기 또는 대규모 조건부 배선**을 의미하며, 유지보수 비용이 현재 이득을 넘어설 수 있다.

- 착수 전 판단 기준: P3-1 이후에도 "무겁다"는 실제 사용자 피드백이 반복되는가?
- 착수한다면 브랜치 분기보다 **`scripts/`의 제거 스크립트**(선택 기능을 걷어내는 방향)가 3개 트리를 동기화하는 것보다 저렴하다.

---

## P5 — FastAPI 상향 검토 결과 (2026-08-10 실측)

P1-2 의 안전망이 갖춰져 상향을 실제로 시도했다. **결론: 지금은 올리지 않는다.**
격리된 venv 에서 `fastapi 0.115.14 → 0.141.1` 로 올려 게이트를 돌린 실측 결과다
(핀은 되돌렸고 저장소는 0.115.x 유지).

| | |
|---|---|
| 대상 | 0.115.14 → **0.141.1** (정식 릴리스 94개, 마이너 26개 라인) |
| 의존성 | starlette 0.46.2 / pydantic 2.13.4 그대로 충족 — **연쇄 상향 불필요** |
| 결과 | **9 failed, 189 passed** |

### 차단 요인 1 — 트랜잭션 경계 붕괴 (P1-3 조건 충족) ⚠️

`test_commit_failure_is_not_reported_as_success` **실패**.

- 0.115.x: 커밋 실패 → 클라이언트 **5xx** (안전)
- 0.141.1: 커밋 실패 → 클라이언트 **201** + 데이터 미저장 → **데이터 불일치**

`yield` 이후의 종료 코드가 **응답 전송 후에** 실행되도록 바뀌었다. 계획서가 예측한
바로 그 시나리오이며, **P1-3(쓰기 경로를 명시적 트랜잭션 컨텍스트로 전환)이 이제
필수 조건이 되었다.** 상향의 선결 과제다.

나머지 3개 경계 케이스(읽기 무커밋 / 쓰기 1회 커밋 / 예외 시 롤백)는 통과했다.

### 차단 요인 2 — 라우트 모델 변경 (테스트 6곳)

`app.routes` 가 더 이상 하위 라우터를 평탄화하지 않는다.

```text
0.115.x : APIRoute 약 40개
0.141.1 : {'_IncludedRouter': 6, 'APIRoute': 2, 'Route': 1, 'Mount': 1}
```

`AttributeError: '_IncludedRouter' object has no attribute 'path'` 로 5개 실패,
`test_read_path_no_commit.py` 는 조회 라우트를 0개로 판정해 실패. 영향 파일:
`tests/test_route_inventory.py`, `tests/test_main.py`, `tests/test_read_path_no_commit.py`,
각 도메인의 `test_*_auto_registered`.

`_IncludedRouter.original_router.routes` 로 재귀하면 고칠 수 있으나 **private API** 다.
라우트 인벤토리를 공개 API 로 얻는 방법(`app.openapi()` 등)으로 바꾸는 편이 낫다.

### 차단 요인 3 — Deprecation 2건

- `ORJSONResponse` — FastAPI 가 Pydantic 으로 직접 직렬화하므로 불필요해졌다
- `Path(..., example=...)` — `examples` 로 교체 (`app/domains/home/api/routers/v1/home.py:75`)

### 착수 순서 (상향을 진행한다면)

1. **P1-3** 먼저 — 0.115.x 에서도 안전하게 적용 가능하므로 상향과 분리해 선행
2. 라우트 인벤토리 테스트를 공개 API 기반으로 재작성
3. deprecation 2건 정리
4. 그 다음 핀 상향

1번을 건너뛰고 올리면 **쓰기 실패가 성공 응답으로 둔갑**한다. 순서를 바꾸지 말 것.

---

## P4 — 실행 중 발견된 항목 (2026-08-10 추가)

P1~P3 실행 도중 실측으로 드러난 두 건. 검수 보고서에는 없던 내용이다.

### P4-1. 읽기 경로의 불필요한 커밋 제거 + `get_read_session` 실사용

- **증상**: 모든 도메인의 읽기 엔드포인트가 쓰기용 커밋 의존성을 공유해 **매 조회마다 COMMIT** 한다.
  `app/domains/blog/tests/test_transaction_boundary.py` 의 `strict xfail` 이 이를 고정하고 있다.
- **뿌리**: `get_read_session()` 이 replica 라우팅 + 쓰기 차단까지 갖추고 준비되어 있는데
  **어떤 도메인도 쓰지 않는다.** 그래서 도메인 읽기가 전부 writer 로 간다.
- **선례**: `auth` 는 `get_current_user` 를 커밋하지 않는 의존성으로 분리해 이미 해결했다(W2/REQ-009).
  같은 패턴을 나머지 도메인에 적용한다.

대상 (읽기 엔드포인트 13개):

| 도메인 | 읽기 | 쓰기 | 조치 |
|---|---|---|---|
| `home` | 5 | **0** | 기존 `get_access_log_service` 를 비커밋으로 **전환** (병렬 추가 아님 — 쓰기가 없어 커밋 버전은 죽은 코드가 된다) |
| `blog` | 2 | 3 | `get_blog_service_readonly` 추가 |
| `reply` | 2 | 3 | `get_reply_service_readonly` 추가 |
| `sns` | 2 | 3 | `get_sns_service_readonly` 추가 |
| `user` | 2 | 3 | `get_user_service_readonly` 추가 |

- **읽기 의존성은 `get_read_session` 을 쓴다.** 커밋 제거뿐 아니라 replica 라우팅과
  "읽기 핸들러가 몰래 쓰면 즉시 실패" 안전망까지 같이 얻는다. `DB_ROUTER_ENABLED=false`(기본)
  에서는 기존과 동일하게 단일 엔진으로 동작하므로 기본 경로의 위험은 없다.
- **테스트 픽스처 7개**가 `get_session` 만 오버라이드한다. `get_read_session` 도 함께
  오버라이드하지 않으면 읽기 경로가 실제 MySQL 로 새어나간다 — 반드시 같이 고친다.
- **완료 조건**:
  - blog 의 `test_read_path_does_not_commit` xfail 마커 제거 후 통과
  - 5개 도메인 전부에 대해 읽기 경로 무커밋을 검증
  - 기존 190 passed 유지

### P4-3. auth 인증 조회의 읽기 세션 전환

P4-1 이 5개 도메인만 다뤄 `auth` 가 남았다. `get_current_user` 는 커밋은 하지
않았지만 쓰기 세션을 잡고 있어, 인증 조회가 replica 로 분산되지 않았다.

- **조치**: `get_current_user` 의 세션을 `get_read_session` 으로 전환. auth 테스트
  픽스처 2개에 오버라이드 추가.
- **가드 강화**: `tests/test_read_path_no_commit.py` 의 기존 규칙(커밋 의존성 금지)
  만으로는 이 결함을 못 잡는다. "조회 라우트는 쓰기 세션을 쓰지 않는다"를 규칙 2로
  추가했다.
- **결과**: `/api` 하위 조회 라우트 **14개 전부** 읽기 전용 세션 사용.

### P4-2. Alembic 마이그레이션 체인 복구

- **증상**: 빈 DB에서 `alembic upgrade head` 가 실패한다.
  ```text
  sqlalchemy.exc.OperationalError: no such table: users
  [SQL: ALTER TABLE users ADD COLUMN hashed_password VARCHAR(255)]
  ```
- **원인**: baseline(`f4adf0ae24ea`)이 `user_access_logs` **하나만** 생성한다.
  `users`, `blog_posts`, `replies`, `sns_posts` 가 통째로 빠졌다. 다음 리비전
  (`b2f1a9c0d3e4`)이 존재하지 않는 `users` 를 ALTER 하면서 체인이 끊긴다.
  DEBUG 모드의 `create_db_tables()` 가 이 결함을 가려왔다 — 운영(`DEBUG=false`)에서는
  Alembic 이 유일한 스키마 경로이므로 배포가 불가능한 상태다.
- **조치**: baseline 이 누락한 4개 테이블을 생성하도록 **보정한다.**
  - 뒤에 새 리비전을 붙이는 방식으로는 못 고친다 — 실패 지점이 `b2f1a9c0d3e4` 이므로
    그 이전이 온전해져야 한다.
  - `users` 는 `hashed_password` **없이** 생성한다. 그래야 후속 리비전의 ALTER 가
    그대로 의미를 갖고 리비전 해시를 건드리지 않는다.
  - 이 저장소는 배포된 제품이 아니라 템플릿이므로, 이미 적용된 운영 DB를 가정한
    호환 처리는 하지 않는다.
- **완료 조건**:
  - 빈 DB에서 `alembic upgrade head` 성공
  - 업그레이드 결과 스키마와 모델 metadata 가 일치(autogenerate 差分 없음)
  - 회귀 방지 테스트 추가

---

## 실행 순서 및 의존 관계

```text
P1-1 (mypy)  ──────────────┐
                           ├─→ CI 타입 게이트 활성화 가능
P1-2 (트랜잭션 테스트) ────┘
        │
        └─(실패 시)→ P1-3 명시적 트랜잭션 컨텍스트

P2-1 (모델 SSOT) ─→ P2-2 (--register) ─→ P2-3 (등록 누락 테스트)

P3-1 (QUICKSTART) ─(피드백 반복 시)→ P3-2 (프로필 분리)

P4-1 (읽기 무커밋)  ← P1-2 의 xfail 이 완료 판정 기준
P4-2 (Alembic 복구) ← P4-1 과 독립. 병행 가능
```

- P1은 서로 독립이므로 병행 가능.
- P2는 순차. P2-1을 건너뛰고 P2-2를 하면 `--register`가 4곳을 편집해야 해 스크립트가 불필요하게 복잡해진다.
- P3-2는 기본적으로 **보류** 상태로 둔다.

## 각 단계 공통 완료 게이트

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp .pytest_tmp   # 기준: 177 passed 이상
.\.venv\Scripts\python.exe -m ruff check .                     # All checks passed
.\.venv\Scripts\python.exe -m mypy . --cache-dir .mypy_tmp     # P1-1 이후: no issues
```

커밋은 작업 단위(P1-1, P1-2, …)별로 나눈다. 하나의 커밋에 여러 P 항목을 섞지 않는다.

## 의도적으로 계획에 넣지 않은 것

- **디렉터리 구조 재편** — 검수 보고서가 계층 분리를 긍정 평가했다. 손댈 이유가 없다.
- **자동 라우터 스캔 도입** — 명시적 `APPS` 목록은 장점으로 평가되었다. P2-2/P2-3은 이 명시성을 유지한 채 누락만 막는다.
- **의존성 버전 일괄 상향** — P1-2의 검증 테스트가 안전망으로 자리잡기 전에는 FastAPI 상향을 시도하지 않는다.
