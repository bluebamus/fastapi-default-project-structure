# Ledger — orm-raw-repository (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.
>
> **Open 인 Fix 가 0건이어야 다음 Phase 로 넘어간다** (ADR-006).

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | HIGH | INV-9 / AR-009 — drain timeout 후 pending 은 cancel + **await** 되어야 한다 | Fix | Fixed | `resources.DRAIN_WAIT_RATIO` + `test_cancelled_task_cleanup_survives_the_outer_timeout` | `_drain_background_tasks` 가 `drain()` 내부 timeout 과 바깥 `asyncio.timeout` 에 **같은 5초**를 줘, drain 이 pending 을 취소하고 gather 로 회수하려는 순간 바깥 guard 가 끊었다. 태스크의 `finally`(세션 rollback/close)가 실행되지 못한 채 DB dispose 로 넘어감 |
| F-002 | LOW | 기존 계약 — 환경변수는 `config.py` 만 직접 읽는다 | Fix | Fixed | `scripts/review_gate.py` (DEBUG setdefault 제거) | 검수 스크립트가 subprocess 스니펫에서 `os.environ` 을 직접 만져 `test_only_config_reads_environment_directly` 를 깼다. DEBUG 는 `app.openapi()` 결과에 영향이 없어 제거로 해결 |
| F-003 | CRIT | 작업 절차 — 일괄 치환이 대상 외 파일을 훼손하지 않을 것 | Fix | Fixed | `git checkout` 복구 (커밋 전 발견) | PowerShell 루프에서 `Get-Content -Raw` 가 빈 파일에 `$null` 을 돌려주자 `$t.Replace()` 가 **비종료 오류**를 냈고, `$n` 이 이전 반복 값을 유지해 빈 파일 6개(`*/tests/test_db.py` 5개 + `home/tests/test_endpoint.py`)에 다른 파일 내용이 기록됐다. 전량 복구 후 **일괄 치환은 Python 스크립트로만** 수행하도록 절차 변경 |

## 검수 라운드 기록

| 라운드 | 시점 | 범위 | 게이트 결과 | 신규 finding |
|---|---|---|---|---|
| R-1 | 2026-08-13 | Phase 0~1 소급 | 전건 통과 (240 tests) | F-001, F-002, F-003 |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
