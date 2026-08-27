# 검증 보고서 — Round 11 · Round 12

| 항목 | 값 |
|---|---|
| 작성일 | 2026-08-25 (Round 11) · 2026-08-27 (Round 12) |
| 대상 | Round 11: ADR-016 리팩터 + F-026 · **Round 12: F-028~F-039 (§6)** |
| 판정 | **CONVERGED** (Round 12, 2026-08-27) — §6 참조 |
| 환경 | Python 3.14.4 · Windows(개발) · MySQL 8.4 컨테이너(호스트 포트 3308) |

> ⚠️ **Round 11 의 `CONVERGED` 는 철회됐다(2026-08-27).** 아래 §1~§5 는 Round 11 시점의
> 기록이며 **그대로 보존한다** — 무엇을 놓쳤는지가 그 자체로 근거다.
> 당시 391 passed 는 진짜였지만, **결함 12건(F-028~F-039)을 하나도 잡지 못했다.**
> 기존 테스트가 보지 않는 축(취소·프로세스 종료·실제 서버 기동)에 결함이 있었기 때문이다.
> 현재 판정은 **§6 Round 12** 를 보라.

> 이 문서에 적힌 수치는 전부 **실제로 실행해 얻은 값**이며, §6 은 각 수치에
> **그 값을 낸 명령**을 함께 적는다. 실행하지 않은 것은 §5 에 따로 적었다.

---

## 1. 테스트

| 실행 | 결과 |
|---|---|
| `tests/core/test_resources.py` (리팩터 직후) | **13 passed** — 파일 수정 없음 |
| 전체 (MySQL 컨테이너 없음) | 383 passed, **8 skipped** |
| 전체 (MySQL 8.4 기동 후) | **391 passed, 0 skipped** |

### skipped 8건에 대해 — 중요

첫 전체 실행은 `383 passed, 8 skipped` 였다. 이 상태로 "전건 통과"라고 적었다면
**MySQL 통합 8건을 건너뛴 채 초록으로 보였을 것이다.** residual-risk **R-003** 이 경고하는
바로 그 상황이다("실행 안 된 것이 초록으로 보인다").

```bash
docker compose -f compose.test.yaml up -d     # MySQL 8.4, 호스트 포트 3308
# healthcheck 가 healthy 가 될 때까지 대기 (약 11회 폴링)
python -m pytest -q                            # → 391 passed, 0 skipped
docker compose -f compose.test.yaml down -v    # 정리
```

결과 줄의 `skipped` 개수를 보지 않으면 눈치챌 수 없다. 이번엔 컨테이너를 올리고
재실행해 **skipped 0** 을 확인했다.

---

## 2. 검수 게이트

`scripts/review_gate.py` — 코드 변경 후 1회, 문서 변경 후 1회, 총 **2회 전건 통과**.

| # | 검사 | 결과 |
|---|---|---|
| 1 | pytest | PASS |
| 2 | ruff check | PASS |
| 3 | ruff format --check | PASS |
| 4 | mypy | PASS |
| 5 | INV-1 View 가 SQL/세션을 직접 다루지 않음 | PASS |
| 6 | INV-2 Repository/Dependency commit 없음 | PASS |
| 7 | INV-5 Raw Base 가 ORM Base 를 상속하지 않음 | PASS |
| 8 | INV-11 기존 공개 API 불변 | PASS — 제거됨 0 · 상태코드변경 0 |
| 9 | MySQL 테스트 포트 단일 출처 (ADR-008) | PASS |
| 10 | 문서 인용 커밋 도달성 (ADR-009) | PASS — 검사 22건 |
| 11 | 인용 요구 ID 실재 (ADR-014) | PASS — 선언 **73 → 75건** |
| 12 | INV-10 path operation async + 동기 I/O 부재 | PASS — 검사 36건 |
| 13 | charter 인수기준 ↔ 수렴 선언 정합 (ADR-015) | PASS — 열린 칸 0 · 수렴선언 True |

> 표의 13행은 게이트가 보고하는 **검사 11종**을 펼친 것이다(1~4 는 정적 게이트 4종).

**검사 11의 선언 ID 가 73 → 75 로 늘어난 것**이 REQ-007·ADR-016 이 design-baseline 에
정식 등록됐다는 기계 확인이다. 인용만 있고 선언이 없으면 이 검사가 빨개진다(F-022 재발 방지).

---

## 3. 실행 실측 — 실제 앱 기동·종료

`main.app` 의 lifespan 을 열고 닫아 관측했다. 단위 테스트가 아니라 **실물 앱**이다.

### 리팩터 전

```text
[shutdown] 애플리케이션 자원 해제 시작
[shutdown] background task 정리 완료 (0.0ms)
[dispose_engine] Disposing database engines...
[dispose_engine] Main engine disposed
[dispose_engine] Background engine disposed - ALL DONE
[shutdown] DB engine 정리 완료 (0.4ms)
                            ← "해제 완료" 줄이 없다 (F-026)
```

### 리팩터 후

```text
[shutdown] 애플리케이션 자원 해제 시작
[shutdown] background task 정리 완료 (0.0ms)
[dispose_engine] Disposing database engines...
[dispose_engine] Main engine disposed
[dispose_engine] Background engine disposed - ALL DONE
[shutdown] DB engine 정리 완료 (0.4ms)
[shutdown] 애플리케이션 자원 해제 완료      ← 살아났다
```

두 경우 모두 실행 순서는 동일했다.

| 관측 항목 | 리팩터 전 | 리팩터 후 |
|---|---|---|
| 해제 순서 | drain → dispose → listener stop | 동일 |
| `dispose_engine` 실제 호출 | O (`ALL DONE`) | O (`ALL DONE`) |
| 종료 후 `app.state.resources` | `None` | `None` |
| 종료 완료 로그 | **출력 안 됨** | 출력됨 |

---

## 4. 요구사항 회귀 점검

design-baseline §4 의 불가침 제약 **C-1 ~ C-9** 위반 없음.

| 제약 | 확인 방법 |
|---|---|
| C-1 공개 API 불변 | 게이트 검사 8 (INV-11) — 제거 0 · 상태코드변경 0 |
| C-6 shutdown 에서 table drop 금지 | 종료 경로에 DDL 없음 — 실측 로그로 확인 |
| C-7 3306 공유 인스턴스 무접촉 | 기동한 것은 **3308 전용 컨테이너뿐**이고 `down -v` 로 정리. 정리 후 `docker ps` 에 MySQL 컨테이너 없음 |

나머지 제약(C-2~C-5, C-8, C-9)은 이번 변경이 건드리지 않는 영역이다.

**AR-008 확인**: 수용 기준이 "startup 전체가 `try/finally` **또는** 동등한 async context
manager cleanup 으로 보호된다"이므로, 이번 전환은 요구 위반이 아니라 **첫 번째 허용
형태로의 이동**이다.

---

## 5. 검사하지 않은 것 (정직한 범위 표시)

- **부하 상황의 종료**: in-flight 태스크가 실제로 drain timeout 을 넘기는 상황을 부하로
  재현하지 않았다. 해당 경로는 단위 테스트(`test_cancelled_task_cleanup_survives_the_outer_timeout`)로만 검증했다.
- **SIGTERM 실경로**: uvicorn 프로세스에 실제 시그널을 보내 종료시키지 않았다.
  lifespan 컨텍스트를 직접 열고 닫아 관측했다.
  → **Round 12 에서 해소.** `tests/integration/test_uvicorn_lifecycle.py` 가 실제 서버를
  띄우고 Windows `CTRL_BREAK_EVENT` / POSIX `SIGTERM` 으로 종료시켜 순서를 확인한다.
  이 경로를 열자 **F-038**(신호 종료 시 `atexit` 미실행)과 **F-039**(CLI 경로 꼬리 유실)가
  드러났다.
- 🔴 **취소(cancellation) 시나리오** — Round 11 은 이 항목을 **목록에 적지도 않았다.**
  `AsyncExitStack` 을 평문 `try/finally` 로 바꾸면서 취소 안전성을 잃었는데(F-028),
  취소를 시험하는 테스트가 없어 "잃은 것 없음" 이라고 기록했다(F-034).
  **검사하지 않은 것을 목록에서 빠뜨리면, 이 §5 자체가 안전하다는 착각을 만든다.**
  → Round 12 에서 `test_manager_cancellation_still_runs_remaining_cleanup` 로 해소.
- **Celery worker 종료**: 이번 변경 범위 밖이며 워커를 기동하지 않았다(기존 residual-risk 와 동일).
- **다중 worker 환경**: worker 별 pool 이 각각 해제되는지는 단일 프로세스로만 확인했다.

이 목록은 `docs/crp/groups/orm-raw-repository/residual-risk.md` 하단의 기존 미검사 항목과
별개로, **이번 라운드가** 확인하지 않은 것이다.

---

## 6. Round 12 (2026-08-27) — F-028~F-039

| 항목 | 값 |
|---|---|
| 대상 | REQ-010 — 프로세스 종료 신뢰성. 결함 **12건**(F-028~F-039) |
| 판정 | **CONVERGED** — Open Fix 0 · 요구사항 회귀 0 |
| 범위 | Wave 0~8 (계획서 `resource-lifecycle-remediation-plan.md` v2) |

### 6-1. 수치와 그 값을 낸 명령

> 아래는 전부 **이 세션에서 실행한 결과**다. 각 행에 명령을 함께 적는다 —
> 수치만 적힌 문서는 나중에 검증할 수 없다.

| 수치 | 명령 |
|---|---|
| **417 passed · failed 0 · skipped 0** | `pytest -q` (MySQL 8.4 컨테이너 기동 후) |
| MySQL 통합 **8 passed** (409 deselected) | `pytest -q -m mysql --mysql-required` |
| ruff 위반 0 | `ruff check .` → `All checks passed!` |
| 포맷 이탈 0 (261 파일) | `ruff format --check .` |
| 타입 오류 0 (188 소스) | `mypy .` |
| 게이트 **검사 12종 전건 통과** | `python scripts/review_gate.py` |
| MySQL 컨테이너 | `docker compose -f compose.test.yaml up -d --wait` (호스트 포트 3308) |

> **"검사 12종" 과 `[PASS]` 14줄은 다른 수를 센 것이다.** 12 는 검사 함수·도구의 개수이고,
> 14 는 출력 줄 수다 — 계층 검사 하나가 INV-1·INV-2·INV-5 세 줄을 낸다. Round 11 까지의
> "11종" 도 같은 기준이며, 이번에 `check_process_level_tests_collected` 가 더해져 12종이 됐다.

### 6-2. 결함 12건과 각각의 종결 근거

| ID | 무엇 | 종결 근거 |
|---|---|---|
| F-028 | 취소 시 뒤 cleanup 건너뜀 | 중첩 `async with`(ADR-017) + `test_manager_cancellation_still_runs_remaining_cleanup` |
| F-029 | 종료·startup 실패 로그 유실 | listener 소유권을 프로세스로(ADR-018) + 실제 서버 통합 테스트 2건. **변이 검증**: 정리 끝에 `stop_log_listener()` 를 되돌리면 두 테스트가 즉시 red |
| F-030 | 큐 포화 시 종료 실패·핸들 분실 | `enqueue_sentinel()` 오버라이드(stdlib 지정 확장 지점) + `stop_log_listener()` 순서 교정 |
| F-031 | 실제 정지 전에 "완료" 기록 | 종료 로그 위치 정정 + 통합 테스트의 순서 단언 |
| F-032 | engine 하나 실패가 뒤를 중단 | `asyncio.gather(return_exceptions=True)` + `tests/core/test_db_engine_disposal.py` 6건 |
| F-033 | 완료 task 예외 미회수 | `add_done_callback` 회수 |
| F-034 | 문서가 취소 계약을 과대 기술 | `refactoring-report.md` · `shutdown-sequence-analysis.md` · `workflow-guide.md` §11 정정 (실측 대조표 첨부) |
| F-035 | 모듈 독스트링이 실제와 불일치 | `resources.py` 독스트링 재작성 |
| F-036 | 테스트가 가리키는 문서 조항 부재 | charter §2-4 명문화 + 가드 테스트 메시지에서 유령 `ADR-019` 제거 |
| F-037 | `atexit` 의 join 무한 대기 | `TimeoutSentinelListener.stop()` 에 예산 부여 (Wave 3 이 만든 위험을 Wave 5 가 닫음) |
| F-038 | 신호 종료 시 `atexit` 미실행 | `SIGTERM`/`SIGBREAK` 핸들러(ADR-022). 실측: `python main.py` 종료 로그 **20줄 → 31줄** |
| F-039 | CLI 경로 종료 로그 꼬리 유실 | lifespan 끝의 큐 flush(ADR-023) + `test_uvicorn_cli_also_flushes_the_shutdown_tail`. **변이 검증**: flush 무력화 시 즉시 red |

### 6-3. Round 11 과 무엇이 달라졌나

Round 11 의 391 passed 는 **거짓이 아니었다.** 그런데도 위 12건을 하나도 잡지 못했다.
이유는 하나다 — **기존 테스트가 보지 않는 축에 결함이 있었다.**

| 축 | Round 11 | Round 12 |
|---|---|---|
| lifespan 취소 | 검사 없음 (§5 목록에도 없었다) | 회귀 테스트 1건 |
| 실제 서버 프로세스 종료 | 검사 없음 | 통합 테스트 3건 (실제 신호로 종료) |
| 신호별 종료 경로 | 검사 없음 | `SIGTERM`/`SIGBREAK` 회귀 테스트 1건 |
| 통합 테스트 skip | skip 이 초록으로 보임 | `--mysql-required` 로 skip → 실패 |
| 위 테스트의 존속 | — | 게이트 검사 12 가 실재를 기계로 확인 |

그래서 이 라운드의 결론은 "더 이상 결함이 없다" 가 아니라 **"이 축들을 열었고, 열자마자
나온 12건을 닫았으며, 다시 닫히지 않도록 기계 검사를 걸었다"** 이다.

### 6-4. 이번에도 검사하지 않은 것

- **Celery worker 종료** — 워커를 기동하지 않았다 (범위 밖, 기존 residual-risk 와 동일).
- **다중 worker(gunicorn 등) 환경** — 단일 프로세스로만 확인했다.
- **POSIX 실경로** — `SIGTERM` 재-raise 후 `atexit` 이 건너뛰어지는 것은 Windows 에서 실측했다.
  구조가 같아 POSIX 도 동일할 것으로 보지만 **실행하지는 않았다.**
- **`--mysql-required` 를 붙이지 않는 경로** — 옵션을 잊으면 여전히 skip 이다 (R-003 잔여).
- **부하 상황의 종료** — in-flight 태스크가 drain timeout 을 실제로 넘기는 상황은
  단위 테스트로만 재현했다.
