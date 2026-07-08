# FastAPI 저장소 감사 보고서

- **대상**: fastapi-default-project-structure (Repository 패턴 기반 FastAPI 템플릿)
- **일자**: 2026-07-08
- **브랜치**: `audit/full-review-2026-07-08` (main 직접 커밋 없음)
- **패키지 매니저**: uv (Python 3.14.4)
- **전체 작업 이력·회귀표**: [`AUDIT_LEDGER.md`](./AUDIT_LEDGER.md) 참조(append-only 원장)

---

## 1. 요약

| 구분 | 내용 |
|---|---|
| 베이스라인 테스트 | **78 passed / 0 failed** |
| 최종 테스트 | **78 passed / 0 failed** (회귀 0) |
| Ruff (lint) | 시작 clean → 최종 clean (`E/W/F/I/B/C4/UP`) |
| Ruff (format) | 69개 파일 재포맷 적용 → 최종 전부 정렬 |
| mypy | **60 errors → 0 errors** (147 파일, `# type: ignore` 미사용) |
| Bandit | MEDIUM+ **1건 → 0건** |
| 커밋 | 8개 원자적 커밋(chore/style/fix×5/docs) |

**발견/조치 집계**: 결함·개선 **11건 식별** — **7건 수정 적용**, **4건 보류(설계 결정 필요)**.

**설치한 도구**: `bandit==1.9.4` (dev 의존성, 보안 스캔용). Ruff·mypy·pytest 는 기존 dev 그룹에 존재.

**환경 특이사항**: `uv run pytest`(콘솔 스크립트 shim)는 인터프리터 불일치로 `slowapi` 를 못 찾아 실패하지만, `uv run python -m pytest` 는 정상(78 passed). 코드 결함이 아닌 로컬 venv shim 문제 → 테스트/CI는 `python -m pytest` 권장.

---

## 2. 심각도별 발견 목록

### Critical
- 없음.

### High
- 없음. (핵심 인프라—세션/트랜잭션 경계, 백그라운드 태스크 상한·drain, Celery 루프 재사용—은 이전 감사(W1/W2/C1)에서 이미 견고하게 정리되어 있었음.)

### Medium

| # | 위치 | 문제 | 조치 |
|---|---|---|---|
| M1 | `app/domains/auth/services/auth_service.py` | `async` 라우트 경로에서 bcrypt(hash/verify)를 **동기 호출** → 로그인/가입 시 이벤트 루프 수백 ms 블로킹(동시성 저하) | **수정**: `asyncio.to_thread` 로 격리(결과 동일, 논블로킹). `fix(async)` |
| M2 | `app/core/repositories/repository_base.py:117` | 중첩 관계 eager-loading(`"a.b"`)의 2번째 파트를 **문자열**로 `selectinload()` 에 전달 → SQLAlchemy 2.0 에서 런타임 오류(문자열 관계 로딩 제거). 문서엔 "중첩 지원"이라 표기됨(드리프트+잠재버그) | **수정**: mapper 를 따라 실제 관계 속성으로 해석. 현재 프로덕션 미사용(문서 예시만)이라 실사용 회귀 0. `fix(repo)` |
| M3 | `main.py:300` | 바인딩 호스트 `0.0.0.0` 하드코딩 (Bandit B104) | **수정(부분)**: `SERVER_HOST/SERVER_PORT` 설정화(기본값 0.0.0.0 유지=동작 보존, env 로 제한 가능). 완전 차단은 §4 보류. `fix(security)` |

### Low

| # | 위치 | 문제 | 조치 |
|---|---|---|---|
| L1 | `app/core/repositories/repository_base.py` (DML×6) | `Result.rowcount` 접근이 타입상 부정확(`CursorResult` 이어야) | **수정**: `cast("CursorResult[Any]", …)` (런타임 동일). `fix(repo)` |
| L2 | 라우터 6종 `responses=` 상수 / pagination / bcrypt 반환 / middleware / celery / filters / admin | mypy 60건(대부분 제네릭·서드파티 스텁·타입 추론) | **수정**: 타입 명시·TypeVar 바운드·중간변수 타입화·표준 스타렛 타입. mypy override 에 slowapi/bcrypt/celery 추가. `fix(types)` |
| L3 | `app/domains/auth/services/auth_service.py:authenticate` | 사용자 부재 시 bcrypt 미실행 → 응답 시간차로 **사용자명 열거** 가능(타이밍 사이드채널) | **보류(권고)**: §4-③ 참조 |
| L4 | `app/domains/{blog,user,reply,sns}/services` `update_*` | 존재확인 `get_*`(SELECT) 후 `repository.update`(내부 재-SELECT) → 중복 쿼리 | **보류(권고)**: §4-③ 참조 |

---

## 3. FastAPI 특화 점검 결과 (§2)

| 점검 항목 | 결과 |
|---|---|
| async 내 블로킹 호출 | bcrypt만 해당(M1) → **수정**. 그 외 동기 IO(파일/네트워크/DB) 없음(전 도메인 async 드라이버 aiomysql 일관) |
| `response_model` | **전 엔드포인트 지정**(생성/조회/수정=스키마, 삭제=204 No Content). 누락·불일치 없음 |
| Pydantic 검증 공백 | 요청 스키마에 `Field` 제약(min/max_length, 이메일 pattern, `Query(ge/le)`) 적용. 전역 `RequestValidationError` 핸들러가 422 로 일관 변환 → 미검증 500 누출 경로 없음 |
| CORS | 기본값 `allow_origins=["*"] + credentials=False`(**안전 조합**). 위험 조합(`*`+credentials=True)은 운영자가 credentials 를 켤 때만 발생 → 가드 권고(§4) |
| 의존성 주입(Depends) | 요청당 경량 Service/Repository 구성(무거운 재생성 없음). 세션은 `get_session` 이 요청 스코프로 관리, 트랜잭션 경계는 기능 의존성이 yield 후 커밋 — 일관됨 |
| ORM N+1 | 도메인 모델에 `relationship()` **부재** → 현재 N+1 불가. eager-loading 인프라는 제네릭 기반 시설(현 도메인 미사용) |
| 예외 처리 | 조용히 삼키는 `except: pass`·bare `except` **없음**. `except Exception` 4곳은 모두 정당(세션 rollback+재발생, 비핵심 로그 저장 격리). 4종 전역 핸들러가 일관 응답 |

---

## 4. 설계 정합성 검수 결과 (§5)

### 4-① 파악한 저장소 목적·핵심 설계
- **목적**: 실무용 FastAPI 백엔드 **템플릿/표준 구조** 제공(Repository 패턴 + 도메인 주도 레이아웃).
- **아키텍처**: 3계층 `Router(view) → Service → Repository → DB`. 트랜잭션 경계는 UnitOfWork 대신 **기능 의존성(`get_<name>_service`)** 이 담당(yield 후 커밋, 예외 시 세션 teardown 롤백).
- **도메인**: `home, blog, reply, sns, user, auth` 6개. 각 도메인 `__init__.py` 가 `router` 취합 → `main.py` `APPS` 가 최종 등록.
- **인프라**: 메인/백그라운드 커넥션 풀 분리, 백그라운드 태스크 상한+lifespan drain, Celery 영속 루프, 구조화 로깅, slowapi 레이트리밋, JWT/bcrypt 인증, SQLAdmin.
- **실행**: `uv sync` → `.env` 설정 → `uv run uvicorn main:app --reload`(또는 `python main.py`). DEBUG=True 시 테이블 자동 생성·/docs 활성.

### 4-② 정합성 대조 (코드 ↔ 문서) 및 조치

| 항목 | 상태 | 조치(기준: 코드/파일) |
|---|---|---|
| README `cp .env.sample .env` | **드리프트** — 실제 파일은 `.env.example` | 문서 정정 → `.env.example` |
| README `authenticator(스텁)` | **드리프트** — 실제 JWT/bcrypt 완전 구현 | 문서 정정 → 실제 구현 반영 |
| 인증(JWT/OAuth2)·레이트리밋(slowapi) | **드리프트** — 코드엔 있으나 README 특징/스택 **미기재** | 문서에 항목 추가 |
| "도메인은 서로 import 안 함" | **부분 위반(의도된 예외)** — `auth→user`(횡단 관심사, 코드에 명시) | 문서 규칙에 예외 명시 |
| "core는 절대 domains import 안 함" | **부분 위반(실용 예외)** — `session.py create_db_tables`(DEBUG 전용, 함수 내부) | 문서 규칙에 예외 명시 |
| 계층 경계(router→service→repo) | **일치** — 라우터는 HTTP 역할만, 비즈니스/트랜잭션은 service/dependency | 조치 불요 |
| `response_model`·엔드포인트 | **일치** — 문서화된 CRUD 실제 구현·동작 | 조치 불요 |
| N+1 "Eager Loading 내장" | **부분 드리프트** — 시설은 있으나 현 도메인은 relationship 없어 미사용(예시 코드의 `user.posts` 는 실제 모델에 없음) | 코드 예시는 설명용으로 유지, 보고서에 명시 |

> 문서-코드 불일치는 **모두 코드/파일 실제 상태를 기준(ground truth)** 으로 삼아 문서를 정정했다. 근거: 최근 커밋 이력(`feat(auth)`, `feat: slowapi`)이 코드 쪽 최신성을 뒷받침하고, 테스트(78 passed)가 코드 동작을 보증.

### 4-③ 설계·워크플로 평가 및 보류 항목(설계 결정 필요)

전반적으로 관심사 분리·결합도·에러 처리·동시성 모델이 **일관되고 건전**하다. 아래는 자동 적용하지 않고 남긴 판단 항목:

1. **CORS 가드 (권고)**: 현재 기본값은 안전하나, 운영자가 `CORS_ALLOW_CREDENTIALS=true` 를 켜면서 `CORS_ALLOW_ORIGINS=["*"]` 를 남기면 자격증명 포함 임의 출처 허용(취약). → `CORSSettings` 에 두 값 조합을 거부하는 `model_validator` 추가 권고. (동작 변경 소지 있어 보류)
2. **사용자 열거 타이밍(L3, 권고)**: `authenticate` 가 사용자 부재 시 bcrypt 를 건너뛰어 응답 시간차 발생. → 더미 해시 상시 비교로 상수시간화 권고. (보안 설계 선택 — 보류)
3. **update 중복 쿼리(L4, 권고)**: `update_*` 의 사전 존재확인은 `repository.update` 의 rowcount 판정과 중복. → 사전 SELECT 제거로 1쿼리 절약 가능(에러 메시지 동일). (경미, 보류)
4. **B104 완전 차단(M3 잔여)**: 기본 바인딩을 `127.0.0.1` 로 바꾸면 컨테이너 외부 접근이 막혀 의도된 실행 방식이 깨짐 → 기본값 0.0.0.0 유지, 운영 제한은 배포 시 `SERVER_HOST` 주입으로 결정 필요.
5. **README 인증/레이트리밋 상세 섹션(권고)**: 특징·스택엔 추가했으나, 엔드포인트(`/api/v1/auth/*`)·토큰 수명·레이트리밋 한도 문자열에 대한 **전용 사용 섹션**은 미작성(대규모 문서 추가라 보류).

### 4-④ 회귀 방지 비교표
[`AUDIT_LEDGER.md` — "회귀 방지 비교 검수 표"](./AUDIT_LEDGER.md) 참조. 이전 감사(W1/W2/C1)에서 해결한 상태로 되돌아간 변경 **없음**.

---

## 5. Human decision / 설계 결정 필요 목록

| 항목 | 권고안 |
|---|---|
| **시크릿 배포값 주입** | 이번 감사에서 하드코딩 시크릿 이전은 없었음(기존에 이미 `.env`/설정 기반). 단, 배포 시 `ACCESS_TOKEN_SECRET_KEY`/`REFRESH_TOKEN_SECRET_KEY`/DB·Redis 비밀번호 등 `.env.example` 키들의 실제 값 주입 필요(코드 변경 아님, 배포 절차) |
| **`SERVER_HOST` (M3)** | 민감 환경은 `SERVER_HOST=127.0.0.1` + 리버스 프록시. 기본은 컨테이너용 0.0.0.0 유지 |
| **CORS 조합 가드** | `["*"]`+credentials 거부 validator 도입 여부 결정 |
| **타이밍 사이드채널(L3)** | 상수시간 인증(더미 해시) 채택 여부 결정 |
| **update 중복 쿼리(L4)** | 사전 존재확인 제거 여부 결정 |
| **인증/레이트리밋 문서 섹션** | README 전용 사용 섹션 보강 여부 결정 |

---

## 6. 다음 단계 제안

1. **CI 게이트 도입**: `ruff check` + `ruff format --check` + `mypy .` + `bandit -ll -r app main.py config.py` + `python -m pytest` 를 PR 필수 체크로. (전부 현재 통과 상태이므로 즉시 게이팅 가능)
2. **pre-commit**: ruff(lint+format)·mypy 훅으로 로컬 단계 차단.
3. **테스트 실행 표준화**: 콘솔 스크립트 shim 문제를 피하려 `python -m pytest` 를 문서/CI 표준으로 명시.
4. **bandit 상시화**: dev 그룹에 이미 추가됨 — CI 에서 `-ll`(MEDIUM+) 게이트.
5. (선택) Ruff `select` 에 보안 룰 `S` 편입(테스트 디렉터리 `S101` 제외) — 이번엔 별도 스캔으로만 확인.

---

### 부록 · 커밋 목록
```
7700662 docs: fix README drift vs code (auth/rate-limit/env/arch exceptions)
f850393 fix(async): offload bcrypt hashing/verify to threadpool
0f3d9d4 fix(security): make dev server bind host/port configurable (B104)
0df11c9 fix(types): resolve all mypy errors without type: ignore
305e535 fix(repo): nested eager-loading correctness + rowcount typing
bddecae style(format): apply ruff format across codebase
042401b chore(dev): add bandit for security scanning
```
