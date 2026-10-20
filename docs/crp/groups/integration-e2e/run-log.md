# Run Log — integration-e2e (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안
> 바뀌었으면 동일 요청은 "할 일 없음".

작업 기준선 base SHA: `292ba5b` (main, logging-overhaul 병합). 브랜치 `feat/integration-e2e`.
커밋 `0c7b3e1`(W0) · `7ab06a8`(L1 결함) · `4c2665f`(W1·W2·W5) · `ff88183`(W3·W4) · `abe5d55`(W6) · `9513a83`(F-006·README) · `d1bcaa8`(F-007), 문서는 그룹 개설 커밋.

## 계획 (writing-plans 요약)

계획서(작업 폴더 `integration-test-plan.md`)가 이미 작업·테스트 계획이라 별도 계획 문서는 만들지 않고 실행 순서만 정했다.

1. W0 — Redis 대상 명시(TDD: 실패 확인 → 구현 → fail-on-revert) → 별도 커밋.
2. 병합된 main 에서 인벤토리 재추출(아래), 계획서 §1 과 차이 기록.
3. W1·W2 — `compose.e2e.yaml` + 하네스(안전 검사 먼저: `check_targets` 테스트 → 스택 상태 테스트).
4. W4 — L2 → L3 → L4 → L5 → L6 순서로 층마다 작성·실행·결함 처리. W3 대조기·비밀값 grep 은 마지막.
5. W6 CI, W7 문서, W9 review 문서. 전체를 Windows(로컬)·Linux(WSL 네이티브 — CI 와 같은 prefork·SIGTERM)에서 실행.

## 인벤토리 재추출 (main `292ba5b`, 실제 앱 import)

| 대상 | 결과 | 계획서 §1 대비 |
|---|---|---|
| API operation | 39 (+ `GET /docs` — `DEBUG=true` 에서만) | 같음. `/docs` 는 E2E(배포 구성 `DEBUG=false`)에서 404 로 확인 |
| 접근 수준 | Public 10 · PublicWrite 4 · LoginRequired 12 · SuperuserRequired 13 (`/docs` 제외) | — |
| 관리 뷰 | 7: `post`·`product`·`user-access-log`(생성·수정 불가)·`reply`·`sales-order`(생성·수정·삭제 불가)·`sns-post`·`user`(생성 불가) | 같음. 뷰별 가능 동작을 인벤토리 칸에 반영(불가 칸은 403 확인 후 N/A) |
| Celery | 태스크 2(`home.aggregate_access_stats`·`home.purge_expired_access_logs`), beat 1(`<crontab: 30 3 * * *>`) | 같음 |
| Redis 접두어 | `admin:sess:`·`admin:user_sessions:`·`admin:rl:login:`·`auth:rt:`·`auth:fam:`·`auth:user:`·`auth:rl:login:`·`auth:rl:register:` + Celery broker·backend | **정정:** 계획서의 `admin:login` 은 Redis 키가 아니라 sqladmin 라우트 이름(`url_for("admin:login")`). 관리 로그인 제한 키는 `admin:rl:login:{ip}:{user}`·`admin:rl:login:{ip}` |
| 설정 | 9 클래스 · 69 필드 | **변경:** config-cleanup 1·2차로 `SMTP_*`·`UPLOAD_*`·`SESSION_EXPIRE_SECONDS`·`API_VERSION` 삭제. logging-overhaul 로 `LogSettings` 13 필드(`LOG_APP_LEVELS`·`LOG_FILE_*`·`LOG_DIR`·`LOG_MAX_SIZE_MB`·`LOG_RETENTION_DAYS`·`LOG_*_FORMAT` 등) |
| 로깅(새 검사 대상) | 모든 실행 경로 같은 형식·헤더(`[app=…]`), `LOG_APP_LEVELS`, 프로세스별 파일(`app.log`·`error.log`·`celery.log`·`celery-error.log`), 자정+크기 회전·`LOG_RETENTION_DAYS`, DSN 계정·설정 비밀값 원문 마스킹, uvicorn CLI 접속 줄 마스킹(config-cleanup F-008) | 계획서 작성 뒤 병합 — L6 에 로깅 항목 추가 |

## 라운드 기록

### Round 1 — 2026-10-20 · W0~W9 · L1~L6
- **트리거:** REQ-001~006(사용자 지시·확정 계획서)
- **결정:** ADR-001~008
- **신규 finding:** MED 1(F-001, Fixed) · LOW 6(F-002·F-006·F-007 Fixed, F-003·F-004 Report, F-005 Accepted)

#### W0 — TDD·fail-on-revert

| 테스트 | 수정 전 코드 |
|---|---|
| `test_missing_redis_port_fails_instead_of_defaulting_to_6379` | 실패(3 skipped — 그리고 **6379 에 실제로 접속했다**: 로컬 6379 는 다른 프로젝트 Redis 라 RED 확인 1회가 그 Redis 에 ping·INFO 를 보냈다. 이후 fail-on-revert 에서는 이 테스트를 빼고 돌렸다) |
| `test_missing_redis_host_fails_too` | 실패(skip 으로 끝남) |
| `test_explicit_but_unreachable_target_keeps_the_skip_policy` | 통과(유지해야 할 정책 — 의도) |
| `test_child_server_gets_the_checked_target_not_the_inherited_one` | 실패(`ServerProcess` 가 대상을 받지 않음) |

복원 방법: 대상 파일을 작업 폴더 밖 tmp 에 복사 → `git show HEAD:…` 로 수정 전 내용 → 테스트 → 복사본으로 복원(diff 동일 확인).

#### 층별 결과 (Windows 로컬 · Linux WSL 네이티브)

| 층 | 테스트 | Windows | Linux |
|---|---|---|---|
| 하네스 | `test_a_stack.py` 8 | 통과 | 통과 |
| L1 회귀 | `test_a_regression.py` 2 — 스택 위 `-m "not mysql"` 1322 passed · `-m mysql --mysql-required` 19 passed | 통과(F-002 수정 뒤) | 통과 |
| L2 | `test_b_api_matrix.py` 275 | 통과 | 통과 |
| L3 | `test_c_flows.py` 13 | 통과 | 통과 |
| L4 | `test_d_admin.py` 57 | 통과 | 통과 |
| L5 | `test_e_faults.py` 4 | 통과 | 통과 |
| L6 | `test_f_ops.py` 12 + `test_zz_secrets.py` 1 | 통과 | 통과 |
| W3 | `test_zz_inventory.py` 2 — 400칸(API 280 · 관리 77 · 관리 요청 17 · Celery 3 · Redis 9 · 장애·운영·로깅 14), 빈 칸 0, N/A 84 | 통과 | 통과 |

전체: Windows **374 passed, 0 skipped** · Linux(WSL 네이티브 클론, `.env` 없음) **374 passed, 0 skipped, 9분 19초**.
`/mnt/c` 위의 Linux 실행은 파일시스템이 느려 import 만 수십 초~수 분 걸려 하네스 시간 제한(90초·300초)에 걸렸다 — 결함이 아니라
환경 문제로 판정하고 WSL 네이티브 경로(`/tmp`, 끝나고 삭제)에서 다시 돌렸다.

#### 측정·관측

- **CSRF 본문 버퍼링 상한(passive R-004 대응 항목의 default 측):** 10 MiB + 1 바이트 폼 본문 → 413(`test_admin_csrf_form_body_over_10_mib_is_413`).
- **Redis 정지:** 관리 화면 503 · 변경 미저장, API 로그인·refresh 500 `INTERNAL_SERVER_ERROR`(내부 정보 없음) + 응답 뒤 연결 종료(F-004), Redis 를 안 쓰는 조회 200, `/ready` 503, 재기동 후 자동 회복.
- **replica 정지:** replica 경로 조회 500 `DATABASE_ERROR`, 쓰기·수정 200, `/ready` 200(R-004). 재기동 후 primary binlog 로 처음부터 따라옴.
- **primary 정지:** `/ready` 503 · `/health` 200 · 쓰기 500(내부 정보 없음). tmpfs 라 스택 재구성.
- **worker 정지:** API 영향 없음, 태스크는 PENDING → 재기동 후 처리.
- **405 `Allow`:** 메서드 분할 경로는 마지막 라우트 메서드만(R-001, 값은 `inventory.md`).
- **Celery 종료:** Linux(prefork·SIGTERM)는 `Warm shutdown` → `worker 자원 해제 완료` → `stop 완료`. Windows(solo·CTRL_BREAK)는 listener 정지 시간 초과(F-005).

#### 검사

최종 코드(`d1bcaa8`) 기준:

| 검사 | 결과 |
|---|---|
| `pytest -m e2e -rsxX` (Windows) | **374 passed**, 1341 deselected, skipped·xfailed 0 — 18분 23초. 인벤토리 빈 칸 0(`inventory.md`), 비밀값 grep 0 |
| `pytest -m e2e -rsxX` (Linux, WSL 네이티브 클론 `9513a83` + 회귀 수정) | **374 passed**, skipped 0 — 9분 19초. Celery prefork warm shutdown·`worker 자원 해제 완료` 확인 |
| L1 `-m "not mysql"`(스택 Redis) | 1322 passed, 393 deselected, skipped 0 |
| L1 `-m mysql --mysql-required`(스택 primary) | 19 passed, skipped 0 |
| `ruff check` · `ruff format --check` | 통과 |
| mypy(격리 실행, 1.20.2) | 205 파일 이상 없음 |
| `review_gate --fast` | 전건 통과(pip-audit 포함) |

관리 화면 모듈은 F-007 수정 뒤 따로 2회(56 passed ×2) 더 돌렸다.

## 수렴 판정

- Round 1: 실패 0 · skip 0 · xfail 0 · 인벤토리 빈 칸 0 · 비밀값 grep 0. 열린 항목은 결정 필요 3건(F-003·F-004·R-004) — 정책·설계 변경이라 보고만 했다.
  **CONVERGED (결정 대기 3건 제외)**
