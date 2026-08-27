# Round 12 진행 현황과 남은 작업

| 항목 | 값 |
|---|---|
| 작성일 | 2026-08-27 |
| 요구 | REQ-010 (프로세스 종료 신뢰성) |
| 근거 계획서 | [`resource-lifecycle-remediation-plan.md`](./resource-lifecycle-remediation-plan.md) (v2, 9 Wave / 10 Task) |
| 진행 | **Wave 0~3 완료 · Wave 4~8 남음** |
| 결함 | F-028 ~ F-037 (10건) — **4건 수정 완료 · 6건 미착수** |
| 마지막 실측 | **395 passed · skipped 0** (MySQL 8.4 기동) · 게이트 **11종 전건 통과** |

---

## 1. 지금 어디까지 왔나

### 완료한 Wave

| Wave | 내용 | 결함 | 증거 |
|---|---|---|---|
| **0** | CRP 진입 — REQ-010·ADR-017·018·021 선언, F-028~F-036 등록 | — | 게이트 검사 9: 선언 75 → 80건 |
| **1** | lifespan 취소 회귀 테스트 추가 | — | **red 확인**: `calls == ['listener_start','drain']` |
| **2** | 종료 조립을 중첩 `async with` 로 전환 | F-028 · F-035 | **기존 13건 무수정 통과** |
| **3** | logging listener 소유권을 프로세스로 (`atexit`) | F-029 · F-031 | startup 실패 출력 **14줄 → 198줄** |

### 결함 상태

| ID | 심각도 | 상태 | 담당 Wave |
|---|---|---|---|
| F-028 | MED | **수정 완료** (close 는 Wave 8) | Wave 2 |
| F-029 | **HIGH** | **수정 완료** (close 는 Wave 8) | Wave 3 |
| F-030 | MED | 미착수 | Wave 5 |
| F-031 | LOW | **수정 완료** (close 는 Wave 8) | Wave 3 |
| F-032 | MED | 미착수 | Wave 4 |
| F-033 | LOW | 미착수 | Wave 4 |
| F-034 | MED | 미착수 | Wave 8 |
| F-035 | LOW | **수정 완료** (close 는 Wave 8) | Wave 2 |
| F-036 | LOW | 미착수 | Wave 6 |
| F-037 | MED | 미착수 — **Wave 3 작업 중 새로 발견** | Wave 5 |

> 수정이 끝난 4건도 원장 Status 는 아직 **Open** 이다. close 는 Wave 7 의 실물 서버 검증을
> 근거로 Wave 8 에서 한꺼번에 한다 — 근거 없는 close 를 하지 않기 위해서다(F-021 의 교훈).

---

## 2. 완료분의 실측 증거

문서가 아니라 **실행 결과**만 적는다.

### F-028 — 취소 시 정리가 끊겼다

버그를 처음 드러낸 스크립트를 리팩터 전후로 그대로 다시 돌린 대조다.

```text
전:  calls = ['listener_start', 'prepare', 'drain']                             state_is_none = False
후:  calls = ['listener_start', 'prepare', 'drain', 'dispose', 'stop_listener']  state_is_none = True
```

취소는 양쪽 모두 정상 재전파된다. 즉 깨져 있던 것은 **"정리를 끝까지 시도한다"** 쪽뿐이었다.

### F-029 — 앱이 안 뜨는데 화면에 아무것도 없었다

DB 가 꺼진 상태에서 `python main.py` 를 실행한 결과다.

| | 이전 | 이후 |
|---|---:|---:|
| 총 출력 줄 수 | 14 | **198** |
| `Application startup failed` | 0 | **1** |
| Traceback | 0 | **2** |
| SQLAlchemy 오류 상세 | 0 | **45줄** |

순서도 계약대로다 — `[app=uvicorn] Application startup failed. Exiting.` **뒤에**
`[log-lifecycle] stop 시작 / stop 완료` 가 온다. listener 가 uvicorn 의 마지막 로그보다
오래 살아남았다는 뜻이다.

---

## 3. 남은 작업 — 순서대로

### Wave 4 — 자원별 실패 격리 〔F-032 · F-033〕

두 Task 는 파일이 겹치지 않아 **병렬**이다.

- **Task 4 (F-032, MED)** — `dispose_engine()` 을 `asyncio.gather(..., return_exceptions=True)`
  로 바꿔 engine 하나의 실패가 나머지를 막지 않게 한다.
  **공개 시그니처는 바꾸지 않는다** — Celery 호출부(`app/celery/lifecycle.py:46`)가 그대로
  동작해야 한다. 신규 `tests/core/test_db_engine_disposal.py`.
- **Task 5 (F-033, LOW)** — `BackgroundTaskRunner` 의 done callback 을 명명 메서드로 분리하고
  `task.exception()` 을 회수해 `Task exception was never retrieved` 를 없앤다.

### Wave 5 — 로깅 구성 표준화 〔F-030 · **F-037**〕

**남은 것 중 가장 중요하다.** Wave 3 이 만든 위험을 닫는다.

1. `TimeoutSentinelListener` — `enqueue_sentinel()` 오버라이드 + **join 에도 예산**(F-037)
2. `stop_log_listener()` 의 **두 줄 순서 교체** — 성공한 뒤에만 참조를 버린다(F-030)
3. `build_dictconfig()` 를 **`dictConfig` 네이티브 선언**으로 전환
   (`class`/`queue`/`listener`/`handlers`). 실현 가능성은 **10개 항목 실측 완료**.

> 깨질 기존 테스트는 **grep 으로 목록을 만든다** — Wave 3 에서 추정으로 만든 목록이
> 틀렸다(4건이라 적었는데 실제 5건이었다).

### Wave 6 — uvicorn 로거 연결 〔F-036〕 · **사용자 결정 필요**

착수 전에 멈춘다. 대안 **A(단독)** / **A+B** 중 선택.

| 대안 | 내용 |
|---|---|
| A | `build_dictconfig()` 에 uvicorn 3종 로거 포함 → 모든 실행 경로 지원, README 변경 불필요 |
| A+B | A + `run_server()` 추출로 진입점 일원화 |

A 채택 시 선행 조건:

- **ADR-020 을 design-baseline 에 정식 선언.** `ADR-019` 는 근거 문서가 없는 유령 ID 라
  개정할 본문 자체가 없다(F-023 / R-007).
- **F-036 정정** — 가드 테스트가 "charter §2-4 를 개정하라" 고 가리키는데 실제 §2-4 에
  그 비목표가 없다.
- 가드 테스트 `test_dictconfig_has_no_per_app_loggers` 는 삭제하지 않고 허용 목록을
  uvicorn 3종으로 좁힌다 — **확실히 깨진다.**

### Wave 7 — 실제 서버 통합 테스트

lifespan 직접 호출이 아니라 **진짜 uvicorn 프로세스**를 띄워 종료시킨다. F-029 계열은
이것 없이는 다시 놓친다 — 이번엔 사람이 손으로 찾았고, 손으로 하는 것은 다음에 안 한다.

- 정상 종료 1건 + startup 실패 1건 (신규 파일 2개 + conftest)
- Windows `CREATE_NEW_PROCESS_GROUP` + `CTRL_BREAK_EVENT` / POSIX `SIGTERM`
- `stderr=STDOUT` 단일 pipe 로 **순서** 검증
- `DEBUG=false` 로 reloader·DB 자동생성 회피 → MySQL 없이 실행

**이 Wave 가 F-028·F-029 의 close 근거를 만든다.**

### Wave 8 — 문서·게이트 수렴 〔F-034〕

1. F-028 ~ F-037 을 각각 근거와 연결해 **close**
2. **F-034 정정** — `refactoring-report.md` 의 "잃음 없음", `shutdown-sequence-analysis.md` 의
   "의미 동일", `verification-report.md` 의 `CONVERGED`, 그리고 §5 "검사하지 않은 것" 에
   **취소 시나리오가 빠져 있었다**는 사실
3. 루트 `conftest.py` 에 **`--mysql-required`** — MySQL 부재를 skip 이 아니라 **실패**로
4. `ARCHITECTURE.md` §4.2 · `workflow-guide.md` §11 갱신
5. checklist 수렴 재선언 — Definition of Done 을 모두 채운 뒤에만

> 금칙어 게이트는 **넣지 않는다.** 문서를 정직하게 쓸수록 빨개지는 검사다(계획서 §4.7).

---

## 4. 순서 제약

| 제약 | 이유 |
|---|---|
| Wave 5 → Wave 6 | Wave 6 이 `build_dictconfig()` 를 건드리는데 Wave 5 가 그 구조를 바꾼다 |
| Wave 3 → Wave 6 | (충족) 표준 실행 명령을 바꾸기 전에 F-029 가 고쳐져 있어야 했다 |
| Wave 4·5·6 → Wave 7 | 실물 검증은 코드가 다 들어간 뒤 |
| Wave 7 → Wave 8 | close 근거가 Wave 7 에서 나온다 |

Wave 4 는 Wave 5·6 과 독립이라 순서를 바꿔도 되지만, **F-037 이 열려 있는 기간을 줄이려면
4 → 5** 가 낫다.

---

## 5. 지금 남아 있는 위험

| 위험 | 상태 |
|---|---|
| **F-037** — `atexit` + `QueueListener.stop()` 의 무한 join | **열려 있다.** 같은 queue 에 소비자가 둘이면 프로세스 종료가 막힌다. 정상 단일 listener 경로는 실측상 정상 종료(exit 0). Wave 5 에서 닫는다 |
| 수정 4건이 Status Open | 의도된 상태. Wave 7 검증 후 Wave 8 에서 close |

---

## 6. 작업 절차에서 배운 것

이번 라운드에 **절차 자체가 두 번 실패**했다. 남겨서 반복하지 않는다.

1. **heredoc 이 백슬래시를 먹었다** (Wave 3). `f"...{message}\n"` 이 파일에 실제 개행으로
   들어가 f-string 이 끊겼다. **이미 메모리에 있던 교훈인데 그 파일에서만 heredoc 을 다시
   썼다.** 두 테스트 파일이 모두 "line 61" 에서 깨져, 원인이 편집한 파일이 아니라 둘 다
   import 하는 제3의 모듈이라는 것을 알아내는 데 시간을 썼다.
   → **백슬래시가 들어갈 파일은 heredoc 을 쓰지 않는다.** 더 나은 선택은 백슬래시가 필요
   없게 코드를 바꾸는 것이다(`print(..., file=stream, flush=True)`).

2. **"깨지는 기존 테스트" 사전 예측이 틀렸다** (Wave 3). 4건을 적었는데 실제 5건이었다.
   목록을 grep 이 아니라 추정으로 만들었기 때문이다.
   → **기대값 문자열을 실제로 검색해 목록을 만든다.**

3. **계획서 §4.4 의 근거가 틀렸다** (Wave 3에서 발견). *"그 스레드는 daemon 이라 프로세스
   종료를 막지 않는다"* 로 join timeout 을 범위 밖에 뒀는데, `atexit` 훅은 daemon 정리보다
   **먼저** 돈다. 계획서를 정정하고 F-037 로 등록했다.
   → 설계 근거에 "~라서 괜찮다" 가 들어가면 **그 문장을 실측으로 확인**한다.

---

## 7. 커밋 이력에 대한 메모

이 커밋 이전까지 **Round 11 과 Round 12 Wave 0~3 이 전부 미커밋 상태**였다. 두 라운드가
같은 문서(design-baseline·ledger·checklist)와 같은 파일(`app/core/resources.py` — Round 11
버전을 Round 12 가 덮었다)을 건드려 **파일 단위로 갈라지지 않으므로**, 되돌아가 라운드별
커밋으로 나누는 것은 실제로 존재하지 않은 이력을 만드는 일이 된다. 그래서 **한 커밋**으로
묶었다.

**Wave 4 부터는 Wave 단위로 커밋한다.** 계획서 §9 의 롤백 계획이 Wave 별 원복을 전제하는데,
한 커밋에 묶여 있으면 그 계획을 실행할 수 없다.
