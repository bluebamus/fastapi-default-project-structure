# 애플리케이션 자원 수명주기 신뢰성 보강 설계·개발 계획서 (v2)

| 항목 | 값 |
|---|---|
| 작성일 | 2026-08-27 |
| 판 | **v2** — v1(2026-08-25)을 타당성 검수 후 개정. 원안은 `resource-lifecycle-remediation-plan-v1-superseded.md` |
| 상태 | **READY FOR IMPLEMENTATION** (Wave 0 승인 후 착수) |
| 선행 문서 | `refactoring-report.md`, `shutdown-sequence-analysis.md`, `verification-report.md` |
| 대상 | FastAPI lifespan, DB engine, background task, process logging listener |
| 결함 | **F-028 ~ F-036** (9건) — 전부 실측으로 재현 |
| 공개 API / DB 스키마 영향 | 없음 |
| 설계 기준 | **관용성 우선** — 표준 라이브러리가 제공하는 것은 직접 만들지 않는다 |

---

## 0. 이 개정본이 v1과 다른 점

v1의 **결함 진단 7건은 전부 타당했고 그대로 승계**한다. 바뀐 것은 **구현 방식**이다.

v1을 검수한 기준은 하나였다 — **"이것이 파이썬/FastAPI에서 통상 쓰는 방법인가."**
난이도가 높거나 관용적이지 않은 구조는, 동작이 옳더라도 6개월 뒤 이 코드를 맡는
사람에게 **읽을 수 없는 코드**가 되므로 채택하지 않는다.

### 0.1 구현 방식이 바뀐 곳 — 표준 라이브러리로 대체

| # | v1이 새로 만들려던 것 | v2가 쓰는 표준 라이브러리 | 근거 |
|---|---|---|---|
| 1 | `_shutdown_application_resources()` 중첩 try/finally coordinator | **중첩 `async with`** | §4.1 — 실측 대조 |
| 2 | `BoundedQueueListener` 3상태 머신 + `RLock` + deadline 공유 | **`QueueListener.enqueue_sentinel()` 오버라이드** + `dictConfig`의 `listener:` 키 | §4.4 — stdlib 독스트링이 지시 |
| 3 | engine별 deadline 분배·재분배 + `ExceptionGroup` | **`asyncio.gather(..., return_exceptions=True)`** | §4.5 |

### 0.2 v1에서 제거한 것

- **금칙어 게이트** (v1 Task 8 step 5) — §4.7에서 기각. 문서 이력을 정직하게
  남길수록 실패하는 검사다.

### 0.3 v1에 없어서 추가한 것

| 추가 | 이유 |
|---|---|
| **Wave 0 — CRP 진입** | v1은 요구·ADR 등록을 마지막 Task 8에 몰아 "코드부터 짜고 요구를 맞추는" 순서였다. ADR-010 위반 |
| **Wave 5 — `dictConfig` 네이티브 전환** | 기존 코드가 Python 3.12+ 표준 기능을 손으로 재구현 중이다(§4.6). 실현 가능성 **실측 완료** |
| **Wave 6 — uvicorn 로거 연결 재설계** | v1은 대안 3개 중 1개를 빠뜨린 채 `uvicorn main:app` 금지로 직행했다(§4.3) |
| **F-035, F-036** | v1이 잡지 못한 결함 2건 |
| 각 Task의 **「깨지는 기존 테스트」** 항목 | v1은 이걸 적지 않아 실행자가 회귀와 의도를 구분할 수 없었다 |
| 결함 ID를 `RL-*` → **`F-028~F-036`** | 이 저장소 원장은 `F-*` 하나뿐이다. 번호판을 새로 만들면 등록부가 갈라진다 |

### 0.4 v1에서 심각도를 조정한 것

| 결함 | v1 | v2 | 근거 |
|---|---|---|---|
| F-028(구 RL-001) 취소 시 정리 중단 | Critical | **MEDIUM** | uvicorn 0.34.3은 lifespan task를 **취소하지 않는다**(§2.3). 현행 운영 경로에서 발현하지 않음 |
| F-029(구 RL-002) 로그 유실 | High | **HIGH (실무 1순위)** | 실측: DB 다운 시 `python main.py`가 오류를 **한 글자도** 출력하지 않음 |
| F-033(구 RL-006) task 예외 미회수 | Medium | **LOW** | asyncio 기본 핸들러가 이미 경고를 출력한다. 조용한 실패가 아니라 소음 |

### 0.5 v1에서 그대로 승계한 것 — 전면 지지

- **Task 7(실제 서버 subprocess 통합 테스트) 2건 모두.** 이 계열 결함은 앱을 실제로
  기동하지 않으면 영원히 보이지 않는다. Windows `CREATE_NEW_PROCESS_GROUP` +
  `CTRL_BREAK_EVENT`, `stderr=STDOUT` 단일 pipe, `DEBUG=false`로 reloader 회피 —
  세부까지 정확하다.
- **`--mysql-required` 옵션.** `pytest_addoption`은 교과서적 pytest 사용법이고,
  residual-risk **R-003**("실행 안 된 것이 초록으로 보인다")을 정확히 겨냥한다.
- **`atexit`로 프로세스 종료 정리.** `atexit`는 그 용도로 존재하는 표준 라이브러리 훅이다.
- **ADR-016을 폐기하지 않고 보완 ADR을 얹는 방식.** append-only 원칙에 맞다.

---

## 1. 목적과 비범위

### 1.1 목적

1. 정상 종료·startup 실패·lifespan 취소 **모두**에서 정리 단계를 끝까지 시도한다.
2. `asyncio.CancelledError`를 삼키지 않고, 필요한 정리를 마친 뒤 호출자에게 재전파한다.
3. background task → DB engine → 상태 참조 제거 순서를 **코드에서 그대로 읽을 수 있게** 한다.
4. process 공용 logging listener를 FastAPI lifespan보다 **긴 수명**으로 관리한다.
5. DB engine 하나 또는 background task 하나의 실패가 나머지 정리를 방해하지 않게 한다.
6. 문서가 선언한 보장 수준과 테스트가 실제로 증명하는 범위를 일치시킨다.
7. **위 전부를 표준 라이브러리의 관용적 사용으로 달성한다.**

### 1.2 비범위

- 공개 API 경로·응답 스키마·상태 코드 변경
- DB 테이블·Alembic migration 변경
- Celery broker/backend 소유권 변경 (AR-006 유지)
- **SIGKILL** 및 uvicorn `force_exit`(Ctrl+C 2회) — 후자는 uvicorn이
  `lifespan.shutdown()`을 **호출조차 하지 않으므로** 애플리케이션 코드로 고칠 수 없다(§2.3)
- logging 포맷·레벨 정책의 전면 개편
- 앱별 로거 등록 일반화 — **예외 없음.** Wave 6은 대안 A를 기각해 앱 `dictConfig`에
  `loggers` 키를 만들지 않는다(ADR-020). uvicorn 3종은 `log_config`으로 분리된다

---

## 2. 현재 상태 — 실측된 사실

### 2.1 검증된 기준선 (2026-08-25 Round 11 시점)

- `tests/core/test_resources.py` — 13 passed (파일 수정 없음)
- 전체 — 391 passed / 0 skipped (MySQL 8.4 컨테이너 기동 후)
- ruff check / ruff format / mypy — 클린
- 검수 게이트 11종 — 전건 통과

**이 초록은 F-028~F-036을 하나도 잡지 못했다.** 기존 테스트가 보지 않는 축
(취소·프로세스 종료·실제 서버 기동)에 결함이 있었기 때문이다. 이 사실 자체가
Wave 1과 Wave 7의 존재 이유다.

### 2.2 결함 목록 — 전부 재현 완료

| ID | 심각도 | 문제 | 영향 파일 | 확인 방법 |
|---|---|---|---|---|
| **F-028** | MEDIUM | lifespan 취소 시 첫 cleanup에서 `CancelledError`가 전파돼 후속 cleanup을 건너뜀 | `app/core/resources.py` | 취소 재현 실행 |
| **F-029** | **HIGH** | listener를 lifespan에서 멈춰 Uvicorn 최종 로그와 **startup 실패 traceback이 유실**됨 | `app/core/resources.py`, `app/utils/logs/setup.py`, `main.py` | **실제 서버 기동** |
| **F-030** | MEDIUM | bounded queue 포화 시 sentinel 삽입 실패 후 listener 참조를 먼저 잃어 회수 불가 | `app/utils/logs/setup.py` | `queue.Full` 주입 |
| **F-031** | LOW | 실제 listener stop 전에 "애플리케이션 자원 해제 완료"를 기록 | `app/core/resources.py` | 코드 |
| **F-032** | MEDIUM | DB engine 하나의 dispose 실패가 뒤 engine 정리를 중단 | `app/core/db/session.py` | 코드 |
| **F-033** | LOW | 완료된 background task의 예외를 회수하지 않음 | `app/core/middlewares/background_tasks.py` | 코드 |
| **F-034** | MEDIUM | 코드 독스트링과 검증 문서가 실제 취소 계약을 과대 기술. `CONVERGED` 선언이 F-028로 반증됨 | 코드 · `docs/` · CRP 문서 | 문서 대조 |
| **F-035** | LOW | `resources.py` 모듈 독스트링 **7행과 13행이 서로 모순** (ExitStack 시절 잔재) | `app/core/resources.py` | 코드 |
| **F-036** | LOW | 가드 테스트가 "charter §2-4를 개정하라"고 지시하는데 **charter §2-4에 그 비목표가 없다** | `tests/utils/test_logs.py`, `charter.md` | 문서 대조 |

### 2.3 F-028 — 실제 발현 조건 (v1이 확인하지 않은 것)

v1은 근거 없이 `Critical`로 매겼다. uvicorn 0.34.3 소스를 확인한 결과는 다음과 같다.

```python
# uvicorn/server.py — graceful timeout 초과 시 취소 대상
for t in self.server_state.tasks:      # 요청 처리 task 들이다. lifespan 이 아니다
    t.cancel(msg="Task cancelled, timeout graceful shutdown exceeded")

if not self.force_exit:
    await self.lifespan.shutdown()     # force_exit 이면 아예 호출되지 않는다

# uvicorn/lifespan/on.py:51 — lifespan task 를 만드는 유일한 곳
main_lifespan_task = loop.create_task(self.main())
#   이 변수는 이후 어디서도 cancel() 되지 않는다
```

| 상황 | 실제 동작 | F-028 발현 |
|---|---|---|
| 정상 종료 (SIGTERM / Ctrl+C 1회) | lifespan 정상 실행 | ✗ |
| graceful timeout 초과 | 요청 task 만 취소, lifespan 무사 | ✗ |
| force_exit (Ctrl+C 2회) | `lifespan.shutdown()` **미호출** — 정리가 통째로 안 됨 | ✗ (별개 문제, 비범위) |
| pytest 하네스 · 다른 ASGI 서버 · 앱을 감싸는 코드 | lifespan task가 취소됨 | **✓** |

**그럼에도 고치는 이유** — 등급이 낮아졌다고 유예 대상이 되지는 않는다.

1. 코드 주석이 *"앞 단계가 실패해도 뒤 단계가 건너뛰어지지 않는다"*고 **명시적으로 약속**하는데 지키지 못한다. 다음 사람을 속인다.
2. 테스트 하네스와 다른 서버에서는 **실제로 터진다.**
3. **안전이 uvicorn의 구현 세부에 의존하고 있다.** uvicorn이 다음 버전에서 lifespan을 취소하도록 바꾸면 그날 조용히 터진다.

### 2.4 F-029 — 실측 대조

DB가 꺼진 상태에서 동일한 startup 실패를 두 실행 경로로 재현했다.

| 실행 방법 | 출력 줄 수 | 오류 원인이 보이나 |
|---|---:|---|
| `python main.py` (= `log_config=setup_uvicorn_logging()`) | **14줄** | ❌ **한 글자도 없음** |
| `uvicorn main:app` (README 표준) | **195줄** | ✅ SQLAlchemy 전문 + `Application startup failed. Exiting.` |

`python main.py`의 마지막 3줄:

```text
[dispose_engine] Background engine disposed - ALL DONE
[shutdown] DB engine 정리 완료 (0.4ms)
[shutdown] 애플리케이션 자원 해제 완료      ← 그리고 프로세스가 그대로 죽는다
```

원인은 순서다.

```
1. lifespan startup 실패 (예외)
2. finally 실행 → … → ★ logging listener 정지  (로그 출구를 닫는다)
3. 예외가 uvicorn 에 도달
4. uvicorn 이 traceback + "Application startup failed" 를 기록
5. 그 record 는 queue 로 들어가고, 소비 스레드는 3번에서 죽었다
6. 사라진다
```

**우리가 우리 로그 출구를, 오류를 기록하기 직전에 닫는다.**

> 지금 이 함정이 드러나지 않은 이유는 README 표준 명령이 `uvicorn main:app`이라
> 우리 queue를 거치지 않기 때문이다. **우연히 안전한 길로 다니고 있었다.**
> 그리고 v1은 표준 명령을 `python main.py`로 **바꾸자**고 한다 — 지금 고장 난 그 경로다.
> 따라서 **F-029 수정이 실행 명령 변경보다 반드시 앞선다**(Wave 3 → Wave 6).

### 2.5 문서에서 정정해야 할 주장 (F-034)

| 문서 | 현재 주장 | 실제 |
|---|---|---|
| `refactoring-report.md` | "잃음 — **없음**" | 취소 안전성을 잃었다 |
| `shutdown-sequence-analysis.md` | `AsyncExitStack`과 평문 `try/finally`의 "의미가 동일" | 취소 상황에서 다르다(§4.1 실측) |
| `shutdown-sequence-analysis.md` | `_run_cleanup()`만으로 후속 cleanup이 보장된다 | `Exception`에 대해서만 참. `CancelledError`는 `BaseException`이라 통과한다 |
| `verification-report.md` | `CONVERGED` · Open Fix 0 · 회귀 0 | F-028로 반증 |
| `verification-report.md` §5 | "검사하지 않은 것" 목록 | **취소 시나리오가 목록에 없다** — 안 한 것을 적는 목록에서조차 빠졌다 |
| `docs/ARCHITECTURE.md` | 종료 순서·실패 격리 계약 불변 | 취소 축에서 불변이 아니었다 |

이 표현들은 **Wave 1의 회귀 테스트가 red → green으로 바뀐 뒤에만** 다시 확정할 수 있다.

---

## 3. 설계 원칙

1. **표준 라이브러리를 먼저 쓴다.** stdlib가 제공하는 동작을 직접 구현하지 않는다.
   구현해야 한다면 그 이유를 ADR에 적는다.
2. **관용성이 최적화보다 우선한다.** 파이썬 표준 지식으로 읽을 수 있어야 한다.
   읽는 사람이 산술을 머릿속으로 시뮬레이션해야 하는 코드는 채택하지 않는다.
3. **소유자가 닫는다.** FastAPI lifespan은 요청 처리 자원만, logging subsystem은
   process 공용 listener를 닫는다.
4. **실패와 취소를 구분한다.** 일반 cleanup 실패는 기록·격리하고, 취소 신호는 최종적으로 재전파한다.
5. **모든 정리를 시도한다.** 선행 단계가 실패하거나 취소돼도 후속 단계와 상태 참조 제거는 실행한다.
6. **성공한 뒤에만 성공 상태를 반영한다.** 전역 참조는 실제 stop 성공 뒤에만 `None`으로 바꾼다.
7. **로그 문구는 관측 사실만 말한다.** 실행 전 "시작", 성공 후 "완료", 부분 완료는 범위를 명시한다.
8. **테스트 없는 보장을 문서에 쓰지 않는다.** 단위 테스트와 실제 process 통합 테스트를 구분해 적는다.

---

## 4. 대안 비교와 결정

### 4.1 lifespan 종료 조립 → **중첩 `async with`** (ADR-017)

같은 취소 시나리오를 세 구조로 실행한 실측이다.

```text
NG  A 평평한 finally (현재)   calls=['drain']                            state_none=False
OK  B 중첩 async with         calls=['drain','dispose','stop_listener']  state_none=True
OK  C AsyncExitStack          calls=['drain','dispose','stop_listener']  state_none=True
```

| 대안 | 장점 | 단점 | 결정 |
|---|---|---|---|
| 평평한 `finally` + 연속 `await` (현재) | 코드 순서 = 종료 순서 | **취소에 첫 단계에서 끊긴다** | 기각 (F-028) |
| **중첩 `async with`** | 파이썬 기본 구문. 획득 순서대로 쓰면 정리는 자동 역순. 취소·예외 안전. 자원 추가는 한 줄 | 자원마다 작은 컨텍스트 매니저가 필요 | **채택** |
| `AsyncExitStack` 복원 | 취소 안전. 조건부 자원에 유리 | **등록 역순**이라 인지 비용 — ADR-016의 원래 불만 | 예비안 |
| 손수 만든 coordinator + 중첩 try/finally (v1안) | 동작은 동일 | stdlib 재구현. 관용적이지 않음 | 기각 |
| `asyncio.shield()` 단독 | — | shield를 await하는 바깥 task가 즉시 취소될 수 있어 완료 보장이 없다 | 금지 |
| `except BaseException: pass` | — | `CancelledError`·`KeyboardInterrupt`·`SystemExit`를 영구 억제 | 금지 |

**채택 구조:**

```python
@asynccontextmanager
async def manage_application_resources(app: FastAPI) -> AsyncIterator[ApplicationResources]:
    resources = ApplicationResources()
    app.state.resources = resources
    # 획득 순서 = 의존 순서. 정리는 그 역순으로 자동 실행된다.
    async with _database(app, resources), _background_tasks(app):
        yield resources
```

각 자원은 평범한 작은 컨텍스트 매니저다.

```python
@asynccontextmanager
async def _background_tasks(app: FastAPI) -> AsyncIterator[None]:
    """가장 안쪽 — DB 를 쓰는 주체이므로 가장 먼저 멈춘다."""
    try:
        yield
    finally:
        await _run_cleanup("background task", ..., BACKGROUND_DRAIN_TIMEOUT_SECONDS)
```

**이 구조가 동시에 해결하는 것 —** ADR-016 당시 발견했던 진짜 결함(정리 callback을
자원 획득 **전에** 등록해 "절반 성공 시 절반 정리"가 한 번도 작동하지 않았던 문제)이
구조적으로 사라진다. 자원을 얻지 못하면 그 컨텍스트에 진입하지 못하므로 정리도 등록되지 않는다.

**ADR-016은 폐기하지 않는다.** ADR-016의 판단(ExitStack의 역순 등록이 읽기 어렵다)은
유효했고, 그것이 지적한 "부분 정리 미작동"도 실재했다. ADR-017은 ADR-016이 **검증하지
않은 축(취소)**을 보완한다.

### 4.2 logging listener 수명 → **process 소유 + `atexit`** (ADR-018)

| 대안 | 평가 |
|---|---|
| lifespan에서 stop 유지 (현재) | Uvicorn 최종 로그·startup traceback보다 먼저 죽는다 → 기각 (F-029) |
| `main.py`의 `uvicorn.run()` 뒤에서만 stop | `uvicorn main:app` CLI 경로에 적용되지 않는다 → 기각 |
| **process logging subsystem + idempotent `atexit` stop** | CLI·직접 실행·일반 정상 종료를 함께 포괄. `atexit`는 그 용도의 표준 훅 → **채택** |

`app.utils.logs.setup`이 listener 생성과 process 종료를 함께 소유한다. SIGKILL과
uvicorn `force_exit`은 비범위다. Celery prefork 자식은 기존 `restart_log_listener()` 후
자기 process의 종료 훅이 현재 전역 listener를 정리한다.

> Python 3.14의 `QueueListener`는 **컨텍스트 매니저**다(`logging/handlers.py:1539`).
> 테스트에서 listener 수명을 다룰 때는 `with listener:` 를 쓴다 — 수동
> start/stop 쌍보다 누수에 강하다.

### 4.3 uvicorn 로거 연결 → **Wave 6에서 결정** (ADR-020 후보)

**v1은 이 문제를 §4.2와 한 덩어리로 묶어 대안 하나를 빠뜨렸다.** 두 문제는 별개다.

- 문제 A: listener를 **언제 멈출 것인가** → §4.2에서 해결
- 문제 B: uvicorn 로거를 **우리 queue에 어떻게 연결할 것인가** → 여기

uvicorn 소스에서 확인한 순서:

```python
# uvicorn/config.py
class Config:
    def __init__(...):
        self.configure_logging()                          # 274행 — uvicorn 이 먼저
    def load(self):
        self.loaded_app = import_from_string(self.app)    # 435행 — 그 다음 앱 import
```

**우리 앱이 import될 때 실행되는 `configure_logging()`이 uvicorn보다 나중이다. 즉 우리가 이긴다.**

#### 판단을 바꾼 실측 (Wave 3 완료 후, 2026-08-27)

이 절의 원안은 **A를 1순위 후보**로 뒀다. 근거는 "CLI 경로에서 오류가 안 보인다"였다.
Wave 3(ADR-018 — listener 소유권을 프로세스로)이 끝난 뒤 두 경로를 **같은 startup
실패(DB 다운)로 실제 기동**해 대조한 결과, 그 근거가 사라졌다.

| | `python main.py` | `uvicorn main:app` |
|---|---:|---:|
| 총 출력 줄 수 | 197 | 196 |
| `Application startup failed` | 1 | 1 |
| Traceback | 2 | 2 |

**정확성은 이미 동일하다. F-029는 Wave 3만으로 해결됐다.** 남은 차이는 로그 포맷
하나뿐이다 — `[app=uvicorn]` 라벨과 타임스탬프 형식.

| 대안 | 장점 | 단점 | 판정 |
|---|---|---|---|
| A. `build_dictconfig()`에 uvicorn 3종 로거 포함 | 모든 실행 경로에서 포맷이 통일된다 | 작동 원리가 *우리 `configure_logging()`이 uvicorn 것보다 나중에 적용된다*는 **uvicorn 내부 import 순서**다. 우리 저장소 안에서 검증할 수 없고, uvicorn이 시점을 바꾸면 조용히 깨진다. `loggers` 키가 생겨 가드 테스트에 구멍을 내야 하고 그걸 정당화할 ADR이 추가로 필요하다 | **기각** |
| **B. `run_server()` 추출 + `uvicorn.run(log_config=...)`** | `log_config`은 uvicorn이 **문서화한 공식 파라미터**다. 파라미터 이름만 보고 동작을 읽을 수 있고, 순서 의존이 없다. **이미 `main.py`가 하던 방식**이라 새 메커니즘이 아니다. 가드 테스트·ADR 카브아웃이 필요 없다. `run_server()`가 생기면 Wave 7이 정상 앱과 실패 앱을 **같은 경로로** 띄울 수 있다 | `uvicorn main:app` CLI 경로의 uvicorn 로그는 기본 포맷으로 나간다 — 오류·traceback은 그대로 보이므로 **손실이 아니라 선택**이고, uvicorn CLI를 쓰는 모든 FastAPI 프로젝트의 기본 모습이다 | **채택 (ADR-020)** |
| C. `uvicorn --log-config <file>` | uvicorn 공식 옵션 | `.json`/`.yaml`/`.ini`만 받는다. 이 프로젝트 설정은 ENV에 따라 **파이썬으로 생성**되므로 파일로 표현할 수 없다 | 기각 |

**결정 기준은 "중급 개발자가 리뷰하고 이어서 작업할 수 있는가"다.** 정확성 이득이 0인
상태에서 남의 라이브러리 내부 순서에 기대는 결합을 새로 들이는 것은 그 기준에 반한다.
`uvicorn main:app`은 **비권장으로 밀어내지 않는다** — README에 두 명령을 병기하고
차이 한 줄을 적는다.

**참고 — A를 채택했다면 선행이 필요했던 것 (지금은 해당 없음):**

`ADR-019`("앱별 로거를 등록하지 않는다")는 **이 저장소에 근거 문서가 없는 유령 ID**다.
이미 `F-023`(Accept-out-of-scope)와 residual-risk `R-007`로 수용됐고, 게이트
`review_gate.LEGACY_UNDECLARED_IDS`가 화이트리스트로 통과시킨다. 따라서 **"ADR-019를
개정한다"는 불가능하다 — 개정할 본문이 없다.**

올바른 절차는 **design-baseline에 실재하는 새 ADR(ADR-020)을 선언**하고, 그것이
uvicorn 3종에 한정한 예외임을 명시하는 것이다. 가드 테스트는 삭제하지 않고
**허용 목록을 정확히 그 3개로 좁혀** 유지한다(임의의 앱 로거 등록은 계속 막는다).

> `ADR-019`는 **재사용하지 않는다.** 코드·테스트 5곳이 그 번호를 "앱별 로거 미등록"의
> 뜻으로 인용 중이라 같은 번호에 다른 결정을 담으면 의미가 충돌한다.
> 이번 개정에서 발번하는 ADR은 **017, 018, 020, 021**이며 **019는 건너뛴다.**

### 4.4 queue 포화 종료 → **`enqueue_sentinel()` 오버라이드** (ADR-021 일부)

Python 표준 라이브러리 `logging/handlers.py`가 직접 답을 적어두었다.

```python
def enqueue_sentinel(self):
    """
    This is used to enqueue the sentinel record.

    The base implementation uses put_nowait. You may want to override this
    method if you want to use timeouts or work with custom queue
    implementations.
    """
    self.queue.put_nowait(self._sentinel)
```

**채택 구현:**

```python
class TimeoutSentinelListener(QueueListener):
    """queue 가 가득 차도 종료 sentinel 을 넣을 수 있게 대기한다.

    기본 구현은 ``put_nowait`` 이라 bounded queue 가 포화면 ``queue.Full`` 을
    던진다. 표준 라이브러리가 이 메서드를 timeout 용 확장 지점으로 지정하고 있다.
    """

    def enqueue_sentinel(self) -> None:
        self.queue.put(self._sentinel, timeout=SENTINEL_ENQUEUE_TIMEOUT_SECONDS)
```

그리고 이 클래스는 **`dictConfig`가 공식 지원하는 `listener:` 키**로 주입한다(§4.6).

`_listener` 참조 유실(F-030의 나머지 절반)은 **두 줄 순서 문제**다.

```python
def stop_log_listener() -> None:
    global _listener
    listener = _listener
    if listener is None:
        return
    listener.stop()        # 실패하면 참조가 남아 재시도 가능하다
    _listener = None       # 성공한 뒤에만 버린다
```

| 대안 | 결정 |
|---|---|
| `enqueue_sentinel` 오버라이드 + 참조 순서 수정 | **채택** |
| `RUNNING/STOPPING/STOPPED` 3상태 머신 + `RLock` + 공유 deadline (v1안) | 기각 — stdlib 확장 지점을 bespoke 서브시스템으로 대체한다. 파이썬 표준 로깅 지식만으로 읽을 수 없다 |

> **join timeout은 Wave 5에서 함께 닫는다 (F-037).**
>
> ~~그 스레드는 daemon이라 프로세스 종료를 막지 않는다~~ — **이 근거는 틀렸다.**
> `atexit` 훅은 daemon 스레드 정리보다 **먼저** 실행되므로, 훅 안의 `thread.join()`이
> 그대로 프로세스 종료를 막는다. Wave 3 작업 중 실제로 관측했다: 같은 queue에 소비자가
> 둘일 때 sentinel을 다른 쪽이 가져가 join이 영원히 대기했고, 테스트가 2분 타임아웃으로
> 끊겼다. 정상적인 단일 listener 경로는 실측상 정상 종료한다(exit 0).
>
> 따라서 `TimeoutSentinelListener`는 sentinel enqueue뿐 아니라 **join에도 예산을 준다.**
> "관측되지 않은 실패에 구조를 만들지 않는다"는 원칙은 유지하되, 이건 **관측된** 실패다.

### 4.5 DB engine 정리 → **`asyncio.gather(..., return_exceptions=True)`** (ADR-021 일부)

```python
async def dispose_engine() -> None:
    """모든 engine 을 정리한다. 하나가 실패해도 나머지를 계속 시도한다."""
    targets = [
        ("writer", engine),
        *((f"reader#{i}", e) for i, e in enumerate(read_engines)),
        ("background", background_engine),
    ]
    logger.info("[dispose_engine] Disposing %d database engine(s)...", len(targets))
    results = await asyncio.gather(
        *(target.dispose() for _, target in targets), return_exceptions=True
    )
    failed = [
        (name, result)
        for (name, _), result in zip(targets, results)
        if isinstance(result, BaseException)
    ]
    for name, result in failed:
        logger.error("[dispose_engine] %s 정리 실패: %r", name, result)
    logger.info(
        "[dispose_engine] ALL DONE — 성공 %d · 실패 %d", len(targets) - len(failed), len(failed)
    )
```

| 항목 | v1안 (deadline 분배) | v2안 (`gather`) |
|---|---|---|
| 전부 시도 | 직접 구현 | **표준 동작** |
| 실패 이름 수집 | O | O |
| 전체 예산 | engine별 시간 분배 + 재분배 알고리즘 | **바깥 `asyncio.timeout(10)` 하나** — 동시 실행이라 분배가 불필요 |
| 공개 계약 | `dispose_engine(*, deadline)`로 **변경** | **유지** — Celery 호출부(`app/celery/lifecycle.py:46`) 무변경 |
| 읽는 비용 | deadline 산술을 시뮬레이션해야 한다 | `gather` 한 줄 |

> v1의 시간 분배 알고리즘이 대상으로 삼는 `read_engines`는 **현재 설정에서 빈 리스트**다
> (`mode: single`, `readers: []`). 길이 0인 리스트를 위한 스케줄러다.
>
> 순차 실행을 유지하고 싶다면 `for` 루프 안 `try/except`도 동일하게 관용적이다.
> **둘 중 무엇이든 좋으나 deadline 재분배는 채택하지 않는다.**
>
> `ExceptionGroup` 승격도 하지 않는다. 호출자(`_run_cleanup`)는 어차피 로깅만 하고,
> 종료 경로에서 dispose 실패가 원래의 종료 원인을 덮으면 안 된다(설계 원칙 4).

### 4.6 로깅 구성 → **`dictConfig` 네이티브 QueueHandler/Listener** (ADR-021)

**Python 3.12부터 `dictConfig`가 QueueHandler와 QueueListener를 네이티브로 구성한다.**
그런데 이 프로젝트는 그 경로를 우회하고 있다.

```python
# app/utils/logs/config.py — 현재
QUEUE_HANDLER: {
    "()": "app.utils.logs.queue_handler.build_queue_handler",   # 커스텀 팩토리
    ...
}
```

`logging/config.py`에서 네이티브 경로는 `class:` 분기 안에만 있다.

```python
if '()' in config:
    factory = c                       # ← 여기로 가면 네이티브 지원을 전부 건너뛴다
else:
    klass = self.resolve(cname)
    if issubclass(klass, logging.handlers.QueueHandler):
        factory = functools.partial(self._configure_queue_handler, klass)
```

그 결과 `setup.py`가 stdlib가 해주는 일을 손으로 한다.

| `setup.py`가 손으로 하는 것 | `dictConfig`가 해주는 것 |
|---|---|
| `_queue_handler` 전역으로 붙잡기 | `logging.getHandlerByName()` |
| `_listener_targets`를 이름으로 조회 (`listener_handler_names()`) | `handlers:` 키 |
| `_listener` 생성·보관 | `listener:` 키 + `handler.listener` |
| "`getHandlerByName`이 나중엔 None이 된다"는 타이밍 주석 | 불필요 |

**채택 형태:**

```python
QUEUE_HANDLER: {
    "class": "app.utils.logs.queue_handler.BoundedQueueHandler",
    "queue": {"()": "app.utils.logs.queue_handler.build_log_queue"},
    "listener": "app.utils.logs.setup.TimeoutSentinelListener",
    "handlers": [CONSOLE_HANDLER],           # production/staging 은 + ERROR_CONSOLE_HANDLER
    "respect_handler_level": True,
    "filters": ["sql_noise", "context"],
    "level": level,
}
```

```python
listener = logging.getHandlerByName(QUEUE_HANDLER).listener
listener.start()
atexit.register(listener.stop)
```

#### 실현 가능성 — **실측 완료 (추정 아님)**

이 프로젝트의 실제 필터·포매터·bounded queue 조합으로 10개 항목을 검증했다.

| # | 검증 항목 | 결과 |
|---|---|---|
| 1 | queue 핸들러 타입 | `BoundedQueueHandler` |
| 2 | bounded queue maxsize 유지 | `10000` |
| 3 | `handler.listener` 자동 생성 | `TimeoutSentinelListener` |
| 4 | 커스텀 listener 클래스 주입 | True |
| 5 | listener 대상 핸들러 연결 | `['StreamHandler']` |
| 6 | handler와 listener의 queue 동일 객체 | True |
| 7 | 필터 부착·순서 | `['SqlNoiseFilter', 'ContextFilter']` |
| 8 | 실제 출력 | True |
| 9 | 포맷(`[app=` 라벨) 유지 | True |
| 10 | `with listener:` 후 스레드 종료 | True |

핸들러 이름이 `console` < `error_console` < `queue` 순이라 알파벳 정렬상 queue가
마지막에 구성되어 `handlers:` 참조가 이미 만들어져 있다. (stdlib에 지연 구성 처리도
있으나 이 프로젝트에서는 의존할 필요가 없다.)

### 4.7 문서 게이트 → **금칙어 검사 기각**

v1 Task 8 step 5는 `잃음 없음`, `평문 try/finally와 의미 동일`, 근거 없는 `CONVERGED`를
문서에서 발견하면 게이트를 실패시키자고 한다. **채택하지 않는다.**

1. **v1 스스로 성립 불가를 인정한다** — *"역사 설명이 아닌 현재 계약에서"*. 정규식은
   서술 맥락과 계약 진술을 구분할 수 없다.
2. **이 프로젝트 규약과 충돌한다.** ADR-010에 따라 문서는 덮어쓰지 않고 이력으로 쌓는다.
   즉 *"예전에 '잃음 없음'이라 적었으나 틀렸다"*는 문장이 **반드시 남는다.**
   이 검사는 **정직하게 기록할수록 빨개진다.**
3. 실효 통제는 이미 있다 — **주장에 검증 명령을 연결한다**는 원장 규약.
   문구를 금지할 것이 아니라 근거를 요구해야 한다.

대신 Wave 8은 **각 주장에 실행한 명령과 그 출력을 붙이는 것**을 인수 기준으로 삼는다.

---

## 5. 목표 구조와 계약

### 5.1 목표 수명주기

```text
process 시작
  └─ logging dictConfig 적용 (queue + listener 네이티브 구성)
      └─ listener.start() + atexit.register(listener.stop)
          └─ FastAPI lifespan startup
              ├─ app.state.resources 설정
              ├─ async with _database(...)          ← 모델 import / DB 준비
              │   └─ async with _background_tasks(...)
              │       └─ yield
              │           ┌─ lifespan shutdown (역순 자동)
              │           │   1. background task drain
              │           │   2. DB writer/readers/background engine dispose (gather)
              │           │   3. app.state.resources = None
              │           └─ 4. "요청 처리 자원 해제 완료" 기록
          └─ Uvicorn lifespan/shutdown 최종 로그  ← listener 가 아직 살아 있어 출력된다
  └─ process 종료 → atexit → logging queue flush + listener stop
```

### 5.2 오류 전파 계약

| 상황 | 필수 동작 |
|---|---|
| cleanup 일반 `Exception` | 해당 자원 실패 기록, 다음 자원 계속, lifespan 원인 예외 보존 |
| 자원 timeout | 자원명·예산 기록, 다음 자원 계속 |
| lifespan `CancelledError` | 모든 후속 cleanup 시도, 상태 참조 제거, **마지막에 취소 재전파** |
| cleanup 중 추가 취소 | 아직 실행하지 않은 필수 정리가 수행되도록 unwind. **취소 억제 금지** |
| DB engine 일부 실패 | `gather`로 전부 시도, engine 이름과 함께 기록. 상위로 던지지 않음 |
| listener stop 실패 | **전역 참조 유지**, 직접 stderr fallback으로 기록, 재시도 가능 |

### 5.3 로그 메시지 계약

- lifespan 시작: `[shutdown] 애플리케이션 요청 처리 자원 해제 시작`
- lifespan 성공: `[shutdown] 애플리케이션 요청 처리 자원 해제 완료`
  (**"애플리케이션 자원"이 아니다** — 이 시점에 listener는 살아 있다. F-031)
- process logging stop의 시작·성공·실패는 **queue를 거치지 않는** 최종 sink
  (`sys.__stderr__`)를 쓴다.
- listener stop 전에는 전체 process 자원 "완료"라고 기록하지 않는다.

---

## 6. 작업 계획

모든 구현 작업은 **실패 테스트를 먼저 작성**하는 TDD 순서로 수행한다.
각 Task는 **「깨지는 기존 테스트」**를 명시한다 — 실행자가 회귀와 의도를 구분할 수 있어야 한다.

---

### Wave 0 — CRP 진입 (문서만, 코드 무변경)

#### Task 0. 요구·결정·결함 등록

- **목적:** 코드를 건드리기 전에 요구와 결정을 등록한다. v1은 이걸 마지막에 몰아
  "코드부터 짜고 요구를 맞추는" 순서였고, 이는 ADR-010 위반이다.
- **read_first:**
  - `docs/crp/groups/orm-raw-repository/charter.md`
  - `docs/crp/groups/orm-raw-repository/design-baseline.md`
  - `docs/crp/groups/orm-raw-repository/ledger.md`
  - 이 계획서
- **files_modified:**
  - `docs/crp/groups/orm-raw-repository/design-baseline.md`
  - `docs/crp/groups/orm-raw-repository/ledger.md`
  - `docs/crp/groups/orm-raw-repository/checklist.md`
- **작업:**
  1. **REQ-010** 선언 — "프로세스 종료 신뢰성: 정상·실패·취소 모든 종료에서 자원 정리를
     끝까지 시도하고, 종료 과정의 로그가 유실되지 않는다."
     (REQ-008·009는 유령 legacy ID이므로 **재사용하지 않는다.**)
  2. **ADR-017** 확정 — 종료 조립을 중첩 async context manager로 한다. ADR-016 보완이며 폐기가 아니다.
  3. **ADR-018** 확정 — logging listener 소유권을 process로 이전하고 `atexit`로 정리한다.
  4. **ADR-021** 확정 — `dictConfig` 네이티브 QueueHandler/QueueListener 구성을 채택하고,
     sentinel timeout은 `enqueue_sentinel()` 오버라이드로 해결한다.
  5. **ADR-020은 Wave 6에서 결정**한다는 사실을 design-baseline에 **미결로 명시**한다.
     (**019는 건너뛴다** — 유령 ID와 의미 충돌을 피하기 위해. 그 사유도 함께 적는다.)
  6. **F-028 ~ F-036**을 ledger에 Open으로 등록한다. 각 행에 재현 근거를 적는다.
  7. design-baseline §2에 이번 요청(v2 계획서 기반 검수·수정)을 기록한다.
  8. **checklist의 수렴 선언을 철회**하고 Round 12를 연다. Open Fix를 등록하면서
     "미닫힘 항목 0개"를 그대로 두면 ledger와 checklist가 서로를 반박한다 — F-024가
     지적한 바로 그 구조다. **게이트 검사 11은 이것을 잡지 못한다**:
     `수렴선언 AND charter 열린 칸`일 때만 실패하므로, charter 12칸이 닫힌 채
     ledger만 Open이 되는 이 조합은 그린으로 통과한다.
- **acceptance_criteria:**
  - `scripts/review_gate.py` 검사 9(인용 요구 ID 실재)가 새 ID 전부에 대해 통과한다.
  - ledger에 F-028~F-036이 있고 전부 Open이다.
  - design-baseline에 REQ-010, ADR-017, ADR-018, ADR-021이 선언돼 있다.
  - ADR-019는 새 결정을 담지 않는다 — 건너뛴 사유만 §3 주석에 기록한다
    (`LEGACY_UNDECLARED_IDS`는 변경하지 않는다).
  - **ledger의 Open Fix 수치와 checklist의 수렴 선언이 일치한다.**
  - 게이트 11종이 전건 통과한다(검사 9의 선언 건수가 새 ID만큼 증가).
- **verification:**
  - `.\.venv\Scripts\python.exe scripts\review_gate.py`
- **깨지는 기존 테스트:** 없음
- **dependencies:** 없음 · **STOP: 사용자 승인 후 Wave 1 착수**

---

### Wave 1 — 취소 회귀 재현

#### Task 1. lifespan 관리자 취소 회귀 테스트 추가

- **목적:** F-028을 기존 테스트의 false green에서 분리한다.
  **이 테스트가 없었기 때문에 Round 11이 13/13 green으로 CONVERGED를 선언했다.**
- **read_first:**
  - `app/core/resources.py`
  - `tests/core/test_resources.py`
  - `docs/2026-08-25/shutdown-sequence-analysis.md`
- **files_modified:** `tests/core/test_resources.py`
- **작업:**
  1. 가짜 drain이 `asyncio.Event`에서 대기하도록 구성한다.
  2. `manage_application_resources()`를 **별도 task**로 실행하고, 본문은 즉시 끝내
     `finally`에 진입시킨다. (본문에서 무한 대기하면 shutdown에 도달하지 못한다.)
  3. drain 진입을 확인한 뒤 **manager task 자체**를 `cancel()`한다.
  4. 다음을 검증한다 — dispose 호출됨 · `app.state.resources is None` ·
     호출자가 `CancelledError`를 받음.
  5. Wave 3 이전 단계이므로 listener stop 호출도 임시 기준선으로 검증하고,
     **Wave 3 완료 후 "lifespan에서 stop하지 않음"으로 기대값을 갱신**한다.
     그 갱신 지점을 테스트에 주석으로 남긴다.
- **acceptance_criteria:**
  - 수정 전 새 테스트가 **실패한다**(red 확인이 인수 조건이다).
  - 실패 메시지에 누락된 `dispose` 또는 stale `app.state.resources`가 드러난다.
  - 기존 `test_cancelled_task_cleanup_survives_the_outer_timeout`(자식 task 취소)과
    이름·목적이 명확히 구분된다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\core\test_resources.py -k "manager and cancel"`
- **깨지는 기존 테스트:** 없음 (신규 테스트만 추가)
- **dependencies:** Task 0

---

### Wave 2 — 취소 안전한 종료 조립

#### Task 2. 중첩 async context manager로 전환

- **목적:** 고정 순서의 가독성을 유지하면서 취소·예외 안전 unwind를 **표준 구문으로** 확보한다.
- **read_first:**
  - `app/core/resources.py`
  - `tests/core/test_resources.py`
  - 이 계획서 §4.1
- **files_modified:** `app/core/resources.py`, `tests/core/test_resources.py`
- **작업:**
  1. 자원별 컨텍스트 매니저를 만든다 — `_database(app, resources)`, `_background_tasks(app)`.
     각각 `try: yield / finally: await _run_cleanup(...)` 형태다.
  2. `manage_application_resources()`의 본문을
     `async with _database(...), _background_tasks(...): yield resources` 로 바꾼다.
  3. `app.state.resources = None`과 완료 로그는 **`_database` 컨텍스트의 `finally`**에
     둔다(dispose 직후, 가장 바깥). 위치 근거를 주석으로 남긴다.
  4. `_run_cleanup()`은 timeout과 일반 `Exception`만 기록·격리하고 **`CancelledError`는
     억제하지 않는다.** 현재 코드가 이미 그렇지만, 독스트링이 그 한계를 명시해야 한다(F-034).
  5. 모듈 독스트링 **7행("역순 등록으로 강제한다")을 정정**한다 — F-035.
     13행과 모순되는 ExitStack 시절 잔재다.
  6. `_stop_log_listener()` 호출은 이 Task에서 **그대로 둔다**(Wave 3에서 제거).
- **acceptance_criteria:**
  - Task 1의 취소 테스트가 **green**으로 바뀐다.
  - manager가 drain 또는 dispose 중 취소돼도 뒤 단계와 상태 제거가 실행된다.
  - 호출자는 최종적으로 `CancelledError`를 받는다.
  - 정상 종료 순서는 drain → dispose → state clear이다.
  - startup 실패 시에도 이미 만든 자원의 정리를 시도한다.
  - 코드에 `except BaseException: pass`와 회수 없는 `asyncio.shield()`가 없다.
  - 모듈 독스트링에 서로 모순되는 종료 순서 설명이 없다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\core\test_resources.py`
  - `.\.venv\Scripts\python.exe -m ruff check app\core\resources.py tests\core\test_resources.py`
  - `.\.venv\Scripts\python.exe -m mypy app\core\resources.py`
- **깨지는 기존 테스트:** 없어야 한다. **13건이 무수정 통과하는 것이 계약 보존의 증거다.**
  하나라도 깨지면 구조 변경이 계약을 바꾼 것이므로 멈추고 보고한다.
- **dependencies:** Task 1

---

### Wave 3 — logging listener 소유권 이전 (F-029)

#### Task 3. listener를 process 소유로 옮긴다

- **목적:** Uvicorn 최종 로그와 **startup 실패 traceback**까지 같은 queue에서 소비한다.
  **실행 명령 변경(Wave 6)보다 반드시 먼저 끝나야 한다.**
- **read_first:**
  - `app/core/resources.py`
  - `app/utils/logs/setup.py`
  - `app/utils/logs/__init__.py`
  - `tests/utils/test_logs.py`
  - `tests/core/test_resources.py`
  - `app/celery/lifecycle.py`
- **files_modified:**
  - `app/core/resources.py`
  - `app/utils/logs/setup.py`
  - `app/utils/logs/__init__.py`
  - `tests/core/test_resources.py`
  - `tests/utils/test_logs.py`
- **작업:**
  1. **먼저 red를 만든다** — "lifespan 종료 후에도 listener가 살아 있다"는 테스트를 추가한다.
  2. lifespan에서 `start_log_listener()` handle 저장과 `_stop_log_listener()` 호출을 제거한다.
  3. `ApplicationResources.log_listener`와 **사용되지 않는 `_extra`** 필드를 제거한다.
  4. logging 구성 시 **process당 한 번만** `atexit.register(stop_log_listener)`를 등록한다.
  5. start/stop/restart 전역 상태를 idempotent하게 만든다(여러 번 호출해도 안전).
  6. `configure_logging(force=True)`와 Celery fork 후 `restart_log_listener()`가
     **중복 listener를 만들지 않게** 한다.
  7. queue를 거치지 않고 `sys.__stderr__`에 쓰는 `_write_listener_lifecycle_status()`를
     추가해 process stop의 시작·성공·실패를 기록한다.
  8. lifespan 완료 로그를 **"요청 처리 자원 해제 완료"**로 좁힌다 — F-031.
- **acceptance_criteria:**
  - FastAPI lifespan 종료 뒤에도 listener가 살아 있다.
  - process stop API를 1회 또는 N회 호출해도 listener 스레드는 하나만 종료된다.
  - process stop의 시작·성공·실패 메시지가 **queue가 아닌 `sys.__stderr__`**에서 관측된다.
  - `ApplicationResources`에 **실제로 소유하지 않는 필드가 없다.**
  - lifespan 완료 로그가 "애플리케이션 자원"이 아니라 "요청 처리 자원"이라고 말한다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\utils\test_logs.py tests\core\test_resources.py`
- **깨지는 기존 테스트 (예상):**
  - `tests/core/test_resources.py::test_shutdown_order_is_drain_dispose_then_listener`
    — listener stop이 더 이상 lifespan 종료 순서에 없다. **의도된 변경**이므로
    기대값을 "drain → dispose → state clear"로 갱신한다.
  - Task 1이 남긴 임시 기준선(listener stop 검증)도 여기서 갱신한다.
- **dependencies:** Task 2

---

### Wave 4 — 자원별 실패 격리 (병렬 가능)

> Task 4·5는 서로 다른 파일만 건드리므로 **완전 병렬**이다.
> (v1은 Task 5를 Task 3에 의존시켰으나 두 작업 사이에 결합이 없다.)

#### Task 4. DB engine 전체 dispose 시도 (F-032)

- **목적:** writer 또는 reader 하나의 실패가 다른 pool 정리를 중단하지 않게 한다.
- **read_first:**
  - `app/core/db/session.py`
  - `app/core/resources.py`
  - `app/celery/lifecycle.py`
  - 이 계획서 §4.5
- **files_modified:**
  - `app/core/db/session.py`
  - `tests/core/test_db_engine_disposal.py` (신규)
- **작업:**
  1. writer 실패 · 중간 reader 실패 · 복수 실패를 재현하는 테스트를 먼저 추가하고 red를 확인한다.
  2. `dispose_engine()`을 §4.5의 `asyncio.gather(..., return_exceptions=True)` 형태로 바꾼다.
  3. 실패한 engine을 **이름과 함께** 기록하고, 상위로 던지지 않는다.
  4. **공개 시그니처 `dispose_engine()`는 변경하지 않는다** — Celery 호출부
     (`app/celery/lifecycle.py:46`)와 `_dispose_db_engines()`가 그대로 동작해야 한다.
  5. 바깥 `asyncio.timeout(DB_DISPOSE_TIMEOUT_SECONDS)`는 `_run_cleanup()`에 그대로 둔다 —
     동시 실행이므로 전체 예산 하나로 충분하다.
- **acceptance_criteria:**
  - writer 실패 뒤 모든 reader와 background dispose가 호출된다.
  - 중간 reader 실패 뒤 후속 reader와 background dispose가 호출된다.
  - 실패 engine의 **이름**이 로그에 나타난다.
  - `dispose_engine`의 시그니처가 변경되지 않았다.
  - Celery 종료 경로가 무변경으로 동작한다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\core\test_db_engine_disposal.py`
  - `.\.venv\Scripts\python.exe -m pytest -q tests\test_celery_bridge.py tests\core\test_resources.py`
- **깨지는 기존 테스트:** 로그 문구를 단정하는 테스트가 있으면 갱신
  (`ALL DONE` 문구를 유지하므로 영향은 없을 것으로 예상. 착수 시 확인한다)
- **dependencies:** Task 0 (코드상 Task 2·3과 독립)

#### Task 5. BackgroundTaskRunner 예외 회수 (F-033)

- **목적:** 완료 task의 `Task exception was never retrieved` 경고를 없앤다.
- **read_first:**
  - `app/core/middlewares/background_tasks.py`
  - `tests/core/test_background_tasks.py`
- **files_modified:**
  - `app/core/middlewares/background_tasks.py`
  - `tests/core/test_background_tasks.py`
- **작업:**
  1. 실패 coroutine과 loop exception handler로 미회수 예외를 재현하고 red를 확인한다.
  2. done callback을 `self._tasks.discard`에서 **명명된 메서드**로 분리한다.
  3. set에서 제거한 뒤 `task.cancelled()`를 확인한다.
  4. 취소되지 않은 task는 `task.exception()`을 호출해 예외를 회수하고 명시적으로 로깅한다.
  5. 정상 완료·취소는 error로 기록하지 않는다.
- **acceptance_criteria:**
  - 실패 coroutine의 예외가 **정확히 한 번** 기록된다.
  - loop exception handler에 `Task exception was never retrieved`가 전달되지 않는다.
  - 정상·취소·timeout drain 테스트가 모두 통과한다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\core\test_background_tasks.py`
- **깨지는 기존 테스트:** 없음 예상
- **dependencies:** Task 0 (Task 4와 병렬)

---

### Wave 5 — dictConfig 네이티브 전환 (F-030)

#### Task 6. 로깅 구성을 표준 선언 방식으로 옮긴다

- **목적:** stdlib가 제공하는 queue/listener 구성을 손으로 하지 않는다. 동시에
  sentinel timeout과 **join timeout(F-037)** 을 stdlib 확장 지점으로 해결한다.
- **다루는 결함:** F-030(참조 유실) · **F-037(프로세스 종료 무한 대기 — Wave 3에서 실측)**
- **read_first:**
  - `app/utils/logs/config.py`
  - `app/utils/logs/setup.py`
  - `app/utils/logs/queue_handler.py`
  - `tests/utils/test_logs.py`
  - 이 계획서 §4.4, §4.6 (실현 가능성 실측표 포함)
- **files_modified:**
  - `app/utils/logs/config.py`
  - `app/utils/logs/setup.py`
  - `tests/utils/test_logs.py`
- **작업:**
  1. queue 포화 stop 실패 · 재시도 · 동시 start/stop 테스트를 먼저 추가하고 red를 확인한다.
  2. `TimeoutSentinelListener`(§4.4)를 `setup.py`에 추가한다.
  3. `build_dictconfig()`의 queue 핸들러를 `"()"` 팩토리에서 **`"class"` + `queue` +
     `listener` + `handlers` + `respect_handler_level`** 선언으로 바꾼다(§4.6).
  4. `setup.py`에서 `_queue_handler`·`_listener_targets` 전역과
     `listener_handler_names()` 조회 로직을 제거하고 `logging.getHandlerByName()`과
     `handler.listener`로 대체한다.
  5. `stop_log_listener()`의 **두 줄 순서를 수정**한다 — stop 성공 뒤에만 참조를 버린다(§4.4).
  6. `getHandlerByName` 타이밍 주석(이제 불필요)을 제거하고, 왜 불필요해졌는지 한 줄로 남긴다.
  7. `configure_logging(force=True)`가 기존 listener를 정상 정지한 뒤에만 재구성하도록 한다.
- **acceptance_criteria:**
  - `logging.getHandlerByName("queue").listener`가 `TimeoutSentinelListener` 인스턴스다.
  - handler와 listener가 **같은 queue 객체**를 공유한다.
  - bounded queue의 `maxsize`가 `LOG_QUEUE_MAX_SIZE`로 유지된다.
  - 필터 순서가 `sql_noise` → `context`로 유지된다.
  - queue 포화 상태에서 stop이 `queue.Full`로 죽지 않는다.
  - **첫 stop 실패 뒤 `_listener`가 기존 인스턴스를 유지한다.**
  - 재시도 성공 뒤 listener 스레드가 종료되고 `_listener is None`이다.
  - ENV 4종(development/test/staging/production) 전부에서 구성이 성립한다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\utils\test_logs.py`
- **깨지는 기존 테스트 (예상):**
  - `listener_handler_names()`를 직접 단정하는 테스트
    (`tests/utils/test_logs.py` 내 `logs_config.listener_handler_names("development") == ["console"]`)
    — 함수를 제거하면 깨진다. 제거 대신 유지할지 착수 시 결정하고 기록한다.
  - `build_dictconfig()`의 handler dict 형태를 단정하는 테스트
- **dependencies:** Task 3

---

### Wave 6 — uvicorn 로거 연결 (설계 결정 포함)

#### Task 7. 대안 A/B 결정 후 구현

- **목적:** uvicorn 3종 로거가 앱과 같은 queue·포맷을 쓰게 하되, **생태계 표준 실행
  명령을 배제하지 않는다.**
- **read_first:**
  - 이 계획서 §4.3 (대안 A/B/C 비교)
  - `app/utils/logs/config.py`, `app/utils/logs/setup.py`
  - `main.py`, `README.md`
  - `tests/utils/test_logs.py` (`test_dictconfig_has_no_per_app_loggers`, `test_uvicorn_shares_the_app_queue`)
  - `docs/crp/groups/orm-raw-repository/charter.md` §2-4
- **files_modified:** (**대안 B 확정** — 2026-08-27 사용자 승인)
  - `docs/crp/groups/orm-raw-repository/design-baseline.md` (**ADR-020 선언 — 대안 A 기각**)
  - `docs/crp/groups/orm-raw-repository/charter.md` (§2-4 정정 — F-036)
  - `main.py`, `README.md`
  - `tests/test_main.py`, `tests/utils/test_logs.py` (F-036 문구)
  - `app/utils/logs/config.py`는 **건드리지 않는다** — 대안 A를 기각했으므로 `loggers` 키가 생기지 않는다.
- **작업:**
  1. **STOP — 대안을 사용자와 확정한다.** → **B 확정.** 근거는 §4.3의 실측: Wave 3 이후
     두 실행 경로의 **정확성이 같아져** A를 살리던 근거가 사라졌고, 남은 이득이 포맷
     하나뿐인 상태에서 uvicorn 내부 순서에 기대는 결합을 새로 들일 이유가 없다.
  2. **ADR-020을 design-baseline에 선언**한다. 내용: uvicorn 로거는 `run_server()`의
     `uvicorn.run(log_config=...)`으로 연결하고 앱 `build_dictconfig()`에는 넣지 않는다.
     **유령 `ADR-019`를 재사용하거나 개정하지 않는다**(§4.3).
  3. **F-036 정정** — 가드 테스트가 "charter §2-4를 개정하라"고 지시하지만 §2-4에는
     해당 비목표가 없고, 메시지는 근거 문서가 없는 `ADR-019`를 인용한다. charter §2-4에
     비목표를 **명시**하고 테스트 메시지가 그 조항을 가리키게 한다. 유령 ID 인용은 지운다.
  4. `main.py`의 `uvicorn.run()` 블록을 `run_server(target="main:app")`으로 추출한다.
     `log_config=setup_uvicorn_logging()` 배선은 **그대로 유지**한다.
     `tool.uv.package = false`는 **변경하지 않는다.**
  5. README에 `uv run python main.py`를 추가하되 `uvicorn main:app`을 **비권장으로
     표시하지 않는다.** 두 명령 모두 오류·traceback을 동일하게 출력하며 차이는 포맷뿐임을
     한 줄로 적는다.
  6. 가드 테스트 `test_dictconfig_has_no_per_app_loggers`는 **좁히지도 뚫지도 않는다** —
     앱 `dictConfig`에 `loggers` 키를 만들지 않으므로 그대로 통과한다.
- **acceptance_criteria:**
  - `run_server()`가 `uvicorn.run`에 `setup_uvicorn_logging()` 결과를 `log_config`으로
    넘긴다(테스트로 고정). 대상 앱은 인자로 교체 가능하다(Wave 7 전제조건).
  - `python main.py`에서 uvicorn 로그가 project 포맷과 `[app=uvicorn]` 라벨로 나온다.
  - `uvicorn main:app`에서 uvicorn 기본 포맷으로 나가되 **오류·traceback은 동일하게** 나온다.
  - 가드 테스트가 **무변경으로 통과**하고, 앱별 로거 추가는 여전히 실패시킨다.
  - design-baseline에 **ADR-020이 실재**하고, `LEGACY_UNDECLARED_IDS`는 변경되지 않았다.
  - charter §2-4와 가드 테스트의 지시가 서로 일치한다(F-036 종결).
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\test_main.py tests\utils\test_logs.py`
  - `.\.venv\Scripts\python.exe scripts\review_gate.py`
- **깨지는 기존 테스트 (예상):**
  - **없음.** `main.py`의 `__main__` 블록은 어떤 테스트도 실행하지 않고, 앱 `dictConfig`는
    바뀌지 않는다. (grep으로 확인: `uvicorn.run` 참조 테스트 0건)
- **dependencies:** Task 3, Task 6 · **STOP: 대안 결정 → B 확정(2026-08-27)**

---

### Wave 7 — 실제 process 검증

#### Task 8. Uvicorn 실제 종료·startup 실패 통합 테스트

- **목적:** lifespan 직접 호출이 아닌 **실제 server process**의 로그 순서를 증명한다.
  F-029 계열 결함은 이 테스트 없이는 다시 놓친다.
- **read_first:**
  - `main.py`, `app/utils/logs/setup.py`
  - `compose.test.yaml`
  - `docs/2026-08-25/verification-report.md`
- **files_modified:**
  - `tests/integration/test_uvicorn_lifecycle.py` (신규)
  - `tests/integration/uvicorn_startup_failure_app.py` (신규)
  - `tests/integration/conftest.py`
- **작업:**
  1. 사용 가능한 임시 포트를 할당한다. 두 subprocess 모두 부모 pytest 환경을 그대로
     상속하지 않도록 `env`를 복사한 뒤 `DEBUG=false`, `ENV=test`,
     `SERVER_HOST=127.0.0.1`, `SERVER_PORT=<allocated>`를 **명시적으로 덮어쓴다.**
  2. 정상 서버를 기동하고 project 로그 포맷과 `[app=uvicorn]` 라벨을 확인한다.
     `DEBUG=false`이므로 `reload=False`이고 startup DB 자동 생성도 실행되지 않는다
     (= MySQL 없이 readiness 지점까지 도달한다).
  3. **Windows**: `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP`으로 시작한 뒤
     `process.send_signal(signal.CTRL_BREAK_EVENT)`를 정상 종료 신호로 쓴다.
     **POSIX**: `SIGTERM`. `terminate()`/`kill()`은 timeout 시 fixture 정리 fallback 전용이다.
  4. subprocess는 `stderr=subprocess.STDOUT`으로 **단일 pipe**를 쓴다. 병합된 stream에서
     `요청 처리 자원 해제 완료` → Uvicorn shutdown 완료 → `sys.__stderr__`의 process
     logging stop 완료 **순서**를 검증한다.
  5. `tests/integration/uvicorn_startup_failure_app.py`에 lifespan 진입 시
     `RuntimeError("intentional startup failure F-029")`를 올리는 FastAPI app을 만들고,
     정상 서버와 **동일한 실행 경로**로 기동한다.
  6. 모든 subprocess에 제한시간과 강제 종료 fallback을 둬 CI hang을 방지한다.
- **acceptance_criteria:**
  - 정상 종료에서 project 포맷의 `[app=uvicorn]`과 `Application shutdown complete`
    (또는 사용 중인 uvicorn 버전의 동등 로그)가 **함께** 관측돼 공유 queue 경로를 증명한다.
  - **startup 실패에서도** project 포맷의 `[app=uvicorn]`, `RuntimeError`,
    `intentional startup failure F-029`, process listener stop 완료가 단일 stream에서 관측된다.
    (= F-029가 실제로 고쳐졌다는 유일한 증거다.)
  - 두 subprocess 출력에 `Started reloader process`가 없고 server process는 하나만 시작된다.
  - `DEBUG=false` 로그와 DB 자동 생성 건너뜀 로그가 관측된다.
  - Windows는 `CTRL_BREAK_EVENT`, POSIX는 `SIGTERM`으로 종료되며, **강제 종료 fallback이
    사용된 경우 테스트 결과와 구분**된다(강제 종료를 정상 종료 근거로 쓰지 않는다).
  - 테스트 후 child process와 listener 스레드가 남지 않는다.
  - Windows/POSIX 분기가 fixture 내부로 격리된다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\integration\test_uvicorn_lifecycle.py`
- **깨지는 기존 테스트:** 없음 (신규). 실측 결과도 0건 — 413 passed.
- **실효성 검증(변이):** 신규 테스트가 결함을 실제로 잡는지 세 가지 변이로 확인했다.
  ①`_install_signal_drain()` 제거 → 정상 종료 테스트 red ②자원 정리 끝에
  `stop_log_listener()` 주입(F-029 재현) → 두 테스트 모두 red ③`log_config=` 제거 →
  두 테스트 모두 red. **②에서 실패 앱의 첫 판이 통과해 설계 결함을 발견했다** — 계획서
  문안대로 lifespan 진입 즉시 `raise` 하면 자원 관리자를 타지 않아 F-029 가 재현되지
  않는다. 실패 지점을 관리자 안쪽으로 옮겼다.
- **선행 필수 — F-038: 해소됨(2026-08-27, ADR-022).** 아래 문제를 먼저 닫고 이 Task를
  진행했다. 잔여 F-039(`uvicorn main:app` CLI 경로)는 이 Task의 실행 경로(`run_server()`)에
  영향이 없어 열어 둔다.
  원래 문제: 인수 조건의 *"process listener stop 완료가 단일 stream에서
  관측된다"*는 **당시 설계로 충족할 수 없었다.** uvicorn은 정상 종료를 마친 뒤
  `capture_signals()`의 `finally`에서 원래 핸들러(`SIG_DFL`)를 복구하고 잡았던 신호를
  **다시 올려**(`uvicorn/server.py:329`) 프로세스를 그 자리에서 끝낸다. 그래서 ADR-018의
  `atexit` 훅이 **신호 종료 경로에서는 실행되지 않고**, queue에 남은 꼬리 로그가 유실된다.
  Wave 6 실물 확인에서 관측했고 최소 재현 스크립트로 확정했다(Windows/CTRL_BREAK_EVENT:
  `ATEXIT_RAN` 미출력·exit=3). **이 테스트를 쓰기 전에 F-038을 먼저 닫는다.**
- **dependencies:** Task 3, 4, 5, 6, 7 · **F-038**

---

### Wave 8 — 문서·게이트 수렴

#### Task 9. 문서·CRP·검증 게이트 갱신

- **목적:** 코드·ADR·결함 원장·검증 결과를 같은 사실로 수렴시킨다.
- **read_first:**
  - 이 계획서
  - `docs/2026-08-25/*.md`
  - `docs/ARCHITECTURE.md`
  - `docs/crp/groups/orm-raw-repository/*.md`
  - `docs/orm-raw-repository/2026-08-13/workflow-guide.md`
- **files_modified:**
  - `docs/2026-08-25/refactoring-report.md`
  - `docs/2026-08-25/shutdown-sequence-analysis.md`
  - `docs/2026-08-25/verification-report.md`
  - `docs/ARCHITECTURE.md`
  - `docs/crp/groups/orm-raw-repository/design-baseline.md`
  - `docs/crp/groups/orm-raw-repository/ledger.md`
  - `docs/crp/groups/orm-raw-repository/checklist.md`
  - `docs/crp/groups/orm-raw-repository/run-log.md`
  - `docs/crp/groups/orm-raw-repository/residual-risk.md`
  - `docs/orm-raw-repository/2026-08-13/workflow-guide.md`
  - `conftest.py` (신규 — 루트)
  - `tests/integration/conftest.py`
  - `scripts/review_gate.py`
- **작업:**
  1. F-028~F-036을 **각각 코드 또는 검증 근거와 연결해** closed로 기록한다.
     근거 없는 close는 하지 않는다(F-021의 실패가 그것이었다).
  2. `refactoring-report.md`의 **"잃음 — 없음"**을 사실대로 정정한다:
     취소 안전성을 잃었고, 그것을 시험하지 않아 몰랐다.
  3. `shutdown-sequence-analysis.md`의 **"의미가 동일"**을 정정하고 §4.1 실측 대조를 싣는다.
  4. `verification-report.md`의 `CONVERGED`를 철회하고, §5 "검사하지 않은 것"에
     **취소 시나리오가 빠져 있었다**는 사실을 기록한다. 재선언은 Definition of Done을
     전부 충족한 뒤에만 한다.
  5. `ARCHITECTURE.md` §4.2를 ADR-017 구조로 갱신하고 변경 이력을 추가한다.
  6. `workflow-guide.md` §11 예시 코드를 중첩 `async with` 구조로 교체한다.
  7. 루트 `conftest.py`에 **`--mysql-required`** 옵션을 추가한다(초기 pytest parsing에
     로드되어야 하므로 루트여야 한다). `tests/integration/conftest.py`의 MySQL fixture는
     이 옵션이 있고 DB가 도달 불가능하면 **skip이 아니라 session 실패**로 처리한다.
  8. 정적 게이트에 **manager 취소 테스트와 process lifecycle 테스트 파일의 존재·실행
     여부**를 포함한다.
  9. 실제 실행한 명령·환경·passed/skipped 수만 기록한다. **skipped 수를 반드시 명시한다.**
  10. **금칙어 검사는 추가하지 않는다**(§4.7). 대신 검증 문서의 각 수치 주장에
      **그 값을 낸 명령**을 붙이는 것을 이 Task의 인수 조건으로 삼는다.
- **acceptance_criteria:**
  - F-028~F-036 각각에 코드 또는 검증 근거가 연결돼 있다.
  - 문서 어디에도 평문 연속 `await`와 `AsyncExitStack`의 **취소 의미가 동일**하다는 주장이 없다.
  - 실행하지 않은 경로를 실행한 것으로 기록하지 않는다.
  - `verification-report.md`의 모든 수치 주장에 그 값을 낸 명령이 붙어 있다.
  - `--mysql-required` 실행에서 MySQL 부재는 **skip이 아니라 실패**다.
  - `CONVERGED`는 Definition of Done을 모두 충족한 뒤에만 복원된다.
  - `scripts/review_gate.py`에 금칙어 검사가 없다.
- **verification:**

```powershell
try {
    docker compose -f compose.test.yaml up -d --wait
    if ($LASTEXITCODE -ne 0) { throw "MySQL test container startup failed" }

    .\.venv\Scripts\python.exe -m pytest -q --mysql-required
    if ($LASTEXITCODE -ne 0) { throw "full test run failed" }

    .\.venv\Scripts\python.exe scripts\review_gate.py
    if ($LASTEXITCODE -ne 0) { throw "review gate failed" }
}
finally {
    docker compose -f compose.test.yaml down -v
}
```

- **깨지는 기존 테스트:** 없음 예상
- **dependencies:** Task 0~8

---

## 7. 테스트 매트릭스

| 영역 | 정상 | 일반 실패 | timeout | 외부 취소 | 재진입/경쟁 | 실제 process |
|---|---:|---:|---:|---:|---:|---:|
| lifespan 조립 (중첩 CM) | 필수 | 필수 | 필수 | **필수 (Task 1)** | 필수 | Task 8 |
| background drain | 기존 | 기존/보강 | 기존 | 기존 자식 취소 + **manager 취소** | 필수 | 간접 |
| DB dispose | 필수 | **engine별 필수** | 필수 | 필수 | 선택 | 간접 |
| logging listener | 필수 | 필수 | **sentinel 포화 필수** | 해당 없음 | **필수** | **필수** |
| uvicorn 로거 연결 | **필수** | — | — | — | — | **필수 (양 경로)** |
| startup failure | 기존 | **필수** | 선택 | 선택 | 필수 | **필수** |

### 전체 검증 순서

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\core\test_resources.py
.\.venv\Scripts\python.exe -m pytest -q tests\core\test_background_tasks.py tests\core\test_db_engine_disposal.py tests\utils\test_logs.py
.\.venv\Scripts\python.exe -m pytest -q tests\integration\test_uvicorn_lifecycle.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy .
.\.venv\Scripts\python.exe -m pytest -q --mysql-required
.\.venv\Scripts\python.exe scripts\review_gate.py
```

MySQL 통합 테스트는 `compose.test.yaml`의 전용 포트(**3308**)와 healthcheck를 쓰고,
결과에서 **skipped 수를 반드시 확인**한다. Round 11에서 `383 passed, 8 skipped`를
"전건 통과"로 적을 뻔한 사고가 residual-risk **R-003**의 실현이었다.

---

## 8. 요구사항 추적

| 요구/품질 속성 | 작업 | 증명 |
|---|---|---|
| 종료 순서 명료성 (REQ-010, ADR-017) | Task 2 | 정상 순서 단위 테스트 + 중첩 `async with` 코드 |
| 취소 안전성 (REQ-010, F-028) | Task 1, 2 | manager 취소 테스트 red→green |
| 실패 격리 (F-030, F-032, F-033) | Task 4, 5, 6 | 실패·timeout·포화 테스트 |
| 로그 완전성 (NFR-008, F-029) | Task 3, 6, 7, 8 | **실제 서버 startup 실패 subprocess 로그** |
| 상태 참조 무효화 | Task 1, 2 | 모든 종료 유형에서 `app.state.resources is None` |
| 관용성·유지보수성 (설계 원칙 1·2) | Task 2, 4, 6 | stdlib 사용 — 중첩 `async with` · `gather` · `enqueue_sentinel` · `dictConfig` 네이티브 |
| 실행 경로 호환 (ADR-020) | Task 7 | `uvicorn main:app`·`python main.py` 양쪽 검증 |
| 문서 신뢰성 (F-034, F-035, F-036) | Task 9 | CRP ledger와 실제 명령 결과 연결 |

---

## 9. 배포·관측·롤백

### 배포 전

1. Task 1의 테스트가 **기존 구현에서 실패**하는지 확인한다(red 없이 green은 무의미하다).
2. Wave별 테스트와 전체 게이트를 모두 통과한다.
3. 실제 Uvicorn process에서 정상 종료·startup 실패 로그를 수집해 문서에 붙인다.
4. multi-worker 사용 시 worker별 listener 스레드가 하나인지 확인한다.

### 관측 항목

- shutdown 단계별 소요 시간과 timeout 횟수
- DB engine별 dispose 실패 수
- logging queue drop 수(`BoundedQueueHandler.dropped`)와 listener stop 재시도 수
- background task 실패·취소 수
- shutdown 후 남은 listener 스레드·child process 유무

### 롤백

| Wave | 실패 시 |
|---|---|
| 0 | 문서만 원복. 코드 무변경 |
| 1 | production 코드 무변경. 실패 재현 테스트와 로그를 **보존**한다 |
| 2 | 중첩 CM 전환을 원복하고 **`AsyncExitStack` 복원**을 대체안으로 적용한다. Task 1의 취소 테스트는 **유지**한다 |
| 3 | logging 소유권 변경만 원복. F-028 수정은 유지 |
| 4 | Task 4·5를 각각 독립적으로 원복 |
| 5 | `dictConfig` 네이티브 전환만 원복하고 `stop_log_listener` 두 줄 순서 수정은 **유지**한다 |
| 6 | ADR-020을 미결로 되돌리고 uvicorn 로거 변경만 원복. F-029 수정(Wave 3)은 유지 |
| 7 | 통합 테스트와 fixture만 격리해 분석한다. **강제 종료 결과를 정상 종료 근거로 쓰지 않는다** |
| 8 | false-positive 게이트만 원복. F-028~F-036의 발견 이력과 검증 로그는 **보존**한다 |

- 데이터·DB 스키마를 변경하지 않으므로 migration rollback은 없다.
- **롤백 후에도 새 회귀 테스트는 삭제하지 않는다.** 기대 계약 변경이 승인된 경우에만 수정한다.

---

## 10. 주요 위험과 대응

| 위험 | 대응 |
|---|---|
| `atexit`가 강제 종료에서 실행되지 않음 | SIGKILL과 uvicorn `force_exit`은 **비범위**로 명시. 정상 SIGTERM 유예 시간을 확보 |
| 취소를 잡은 뒤 재전파하지 않음 | Task 1이 **호출자가 `CancelledError`를 받는지** 강제 |
| process 통합 테스트의 CI hang | readiness·종료·kill 각각에 제한시간과 강제 정리 fixture |
| `dictConfig` 네이티브 전환이 ENV별로 다르게 동작 | ENV 4종 전부에 대한 구성 테스트를 인수 조건에 포함(§6 Task 6) |
| ADR-020 결정을 미룬 채 Wave 6 착수 | Wave 6에 **STOP 체크포인트**를 둠 |
| 유령 `ADR-019`를 재사용해 의미 충돌 | **019를 건너뛴다.** 그 사유를 design-baseline에 기록 |
| Wave 3 이전에 실행 명령을 바꿔 F-029가 기본값이 됨 | Wave 6을 Wave 3 **뒤로** 고정 |
| 문서부터 `CONVERGED`로 닫힘 | Wave 8을 마지막에 고정하고 전체 게이트 결과를 선행 조건으로 둠 |
| 기존 테스트가 깨진 것을 회귀로 오인 | 각 Task에 **「깨지는 기존 테스트」**를 사전 명시 |

---

## 11. Definition of Done

- [ ] lifespan manager가 drain 또는 dispose 중 취소돼도 필수 후속 cleanup을 전부 시도한다.
- [ ] cleanup 후 원래 `CancelledError`가 호출자에게 재전파된다.
- [ ] 정상·startup 실패·timeout·취소 **전부**에서 `app.state.resources is None`이다.
- [ ] logging listener가 lifespan보다 오래 살아 **Uvicorn 최종 로그와 startup 실패
      traceback을 소비한다** — 실제 서버 subprocess 로그로 증명.
- [ ] bounded queue 포화 stop 실패가 listener handle 또는 스레드 누수로 이어지지 않는다.
- [ ] 모든 DB engine이 개별 실패와 무관하게 dispose 시도된다.
- [ ] background task 예외가 회수·기록되고 event loop 미회수 경고가 없다.
- [ ] `uvicorn main:app`과 `python main.py` **양쪽**에서 uvicorn 로그가 앱과 같은 경로로 나간다.
- [ ] 구현이 표준 라이브러리 관용 사용으로 이루어졌다 — 중첩 `async with` · `gather` ·
      `enqueue_sentinel` 오버라이드 · `dictConfig` 네이티브. **stdlib 재구현이 없다.**
- [ ] 단위·정적·전체·MySQL·process lifecycle 검증 결과가 **명령과 함께** 기록된다.
- [ ] 문서와 CRP ledger가 구현 및 실제 검증 결과와 일치한다.
- [ ] 공개 API와 DB 스키마 diff가 0이다.

---

## 12. 구현 완료 후 산출물

1. 수정 코드와 회귀 테스트
2. 실제 Uvicorn 정상 종료 / startup 실패 검증 로그 (원문)
3. ADR-017 · ADR-018 · ADR-020 · ADR-021 과 F-028~F-036 close 근거
4. 갱신된 `refactoring-report.md` · `shutdown-sequence-analysis.md` · `verification-report.md`
5. 전체 검증 명령과 passed/**skipped** 수가 포함된 최종 검증 보고서

---

## 부록 A. v1 → v2 대응표

| v1 ID | v2 ID | v1 Task | v2 Task | 구현 방식 변경 |
|---|---|---|---|---|
| RL-001 | F-028 | Task 1, 2 | Task 1, 2 | coordinator 손수 구현 → **중첩 `async with`** |
| RL-002 | F-029 | Task 3 | Task 3 (+ Task 7) | listener/uvicorn 결합을 **분리** |
| RL-003 | F-030 | Task 6 | Task 6 | 3상태 머신 → **`enqueue_sentinel` 오버라이드 + 두 줄 순서** |
| RL-004 | F-031 | Task 3 | Task 3 | 동일 |
| RL-005 | F-032 | Task 4 | Task 4 | deadline 분배 → **`asyncio.gather`** |
| RL-006 | F-033 | Task 5 | Task 5 | 동일 |
| RL-007 | F-034 | Task 8 | Task 9 | 동일 (+ 금칙어 게이트 제거) |
| — | F-035 | 없음 | Task 2 | **신규** — 독스트링 자체 모순 |
| — | F-036 | 없음 | Task 7 | **신규** — 가드 테스트가 없는 charter 항목을 가리킴 |
| — | — | 없음 | **Task 0** | **신규** — CRP 진입 |
| — | — | 없음 | **Task 6** | **신규** — `dictConfig` 네이티브 전환 |
