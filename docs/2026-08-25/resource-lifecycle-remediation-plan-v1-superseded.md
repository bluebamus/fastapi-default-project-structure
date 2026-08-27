# 애플리케이션 자원 수명주기 신뢰성 보강 설계·개발 계획서

| 항목 | 값 |
|---|---|
| 작성일 | 2026-08-25 |
| 상태 | **READY FOR IMPLEMENTATION** |
| 선행 문서 | `refactoring-report.md`, `shutdown-sequence-analysis.md`, `verification-report.md` |
| 대상 | FastAPI lifespan, DB engine, background task, process logging listener |
| 최우선 결함 | lifespan 관리자 취소 시 후속 cleanup 중단 |
| 공개 API/DB 스키마 영향 | 없음 |

---

## 1. 목적

현재의 중앙집중식 FastAPI lifespan 구조는 유지하면서 다음을 보장한다.

1. 정상 종료, startup 실패, lifespan 취소 모두에서 정리 단계를 끝까지 시도한다.
2. `asyncio.CancelledError`를 삼키지 않고 필요한 정리를 마친 뒤 호출자에게 다시 전파한다.
3. background task → DB engine → 애플리케이션 상태 순서를 코드에서 직접 읽을 수 있게 한다.
4. process 공용 logging listener를 FastAPI lifespan보다 긴 수명으로 관리한다.
5. 하나의 DB engine 또는 background task 실패가 나머지 자원 정리를 방해하지 않게 한다.
6. 문서의 보장 수준과 실제 테스트가 증명하는 범위를 일치시킨다.

### 비범위

- 공개 API 경로, 응답 스키마, 상태 코드 변경
- DB 테이블·Alembic migration 변경
- Celery broker/backend의 소유권 변경
- SIGKILL처럼 프로세스 cleanup 자체가 실행될 수 없는 종료 보장
- logging 포맷이나 로그 레벨 정책의 전면 개편

---

## 2. 현재 상태와 문제 정의

### 2.1 검증된 기준선

- `tests/core/test_resources.py`: 13 passed
- Ruff check/format: passed
- mypy (`app/core/resources.py`): passed
- 별도 취소 재현:

```text
calls = ['listener_start', 'prepare', 'drain']
state_is_none = False
```

lifespan 관리자 태스크를 drain 진입 후 취소하면 DB dispose와 listener stop이 호출되지 않고
`app.state.resources`도 기존 객체를 계속 가리킨다.

### 2.2 결함 목록

| ID | 심각도 | 문제 | 영향 파일 |
|---|---|---|---|
| RL-001 | Critical | `CancelledError`가 첫 cleanup에서 전파되어 후속 cleanup을 건너뜀 | `app/core/resources.py` |
| RL-002 | High | logging listener를 lifespan에서 멈춰 Uvicorn의 최종·startup 실패 로그가 유실될 수 있음 | `app/core/resources.py`, `app/utils/logs/setup.py`, `main.py` |
| RL-003 | High | bounded queue 포화 시 sentinel 삽입 실패 후 listener 참조를 먼저 잃음 | `app/utils/logs/setup.py`, `app/utils/logs/queue_handler.py` |
| RL-004 | Medium | 실제 listener stop 전에 전체 자원 해제 완료를 기록함 | `app/core/resources.py` |
| RL-005 | Medium | 한 DB engine dispose 실패가 뒤 engine 정리를 중단함 | `app/core/db/session.py` |
| RL-006 | Medium | 완료된 background task의 예외를 회수하지 않음 | `app/core/middlewares/background_tasks.py` |
| RL-007 | Low | 코드 독스트링과 검증 문서가 실제 취소 계약을 과대 기술함 | 코드·`docs/`·CRP 문서 |

### 2.3 문서에서 정정해야 할 주장

- `refactoring-report.md`: “잃음 없음”
- `shutdown-sequence-analysis.md`: `AsyncExitStack`과 평문 `try/finally`의 “의미가 동일”
- `shutdown-sequence-analysis.md`: `_run_cleanup()`만으로 뒤 cleanup 실행이 보장된다는 설명
- `verification-report.md`: `CONVERGED`, Open Fix 0, 요구사항 회귀 0
- `docs/ARCHITECTURE.md`: 종료 순서·실패 격리 계약이 불변이라는 변경 이력

이 표현은 RL-001 회귀 테스트가 먼저 추가되고 구현이 통과한 뒤에만 다시 확정할 수 있다.

---

## 3. 설계 근거와 원칙

### 3.1 공식 동작 근거

- Python 3.14의 `asyncio.CancelledError`는 `Exception`이 아닌 `BaseException`이며, cleanup 후
  거의 항상 재전파해야 한다.
- `@asynccontextmanager`의 `try/finally`는 FastAPI lifespan에서 자원을 획득·해제하는 표준 패턴이다.
- `AsyncExitStack`은 중첩된 context manager처럼 등록 역순으로 전체 callback을 unwind한다.
- Python 3.14 `QueueListener.enqueue_sentinel()` 기본 구현은 `put_nowait()`을 사용하므로 bounded
  queue에서는 종료 sentinel 삽입 실패를 별도로 다뤄야 한다.
- FastAPI는 startup/shutdown event의 혼용보다 하나의 lifespan async context manager 사용을 권장한다.

공식 참고 자료:

- <https://docs.python.org/3/library/asyncio-exceptions.html#asyncio.CancelledError>
- <https://docs.python.org/3/library/contextlib.html#contextlib.AsyncExitStack>
- <https://docs.python.org/3/library/logging.handlers.html#logging.handlers.QueueListener>
- <https://fastapi.tiangolo.com/advanced/events/>

### 3.2 설계 원칙

1. **소유자가 닫는다.** FastAPI lifespan은 요청 처리 자원만, logging subsystem은 process 공용
   listener를 닫는다.
2. **실패와 취소를 구분한다.** 일반 cleanup 실패는 기록·격리하지만 취소 신호는 최종적으로 재전파한다.
3. **모든 정리를 시도한다.** 선행 단계가 실패하거나 취소돼도 후속 단계와 상태 참조 제거는 실행한다.
4. **성공 뒤에만 성공 상태를 반영한다.** listener 전역 참조는 실제 stop 성공 뒤에만 `None`으로 바꾼다.
5. **로그 문구는 관측 사실만 말한다.** 실행 전에는 “시작”, 성공 후에는 “완료”, 부분 완료는 범위를 명시한다.
6. **테스트 없는 보장을 문서에 쓰지 않는다.** 단위 테스트와 실제 process 통합 테스트를 구분한다.

---

## 4. 대안 비교와 결정

### 4.1 lifespan cleanup 조립

| 대안 | 장점 | 단점 | 결정 |
|---|---|---|---|
| `AsyncExitStack` 복원 | BaseException 발생에도 전체 callback unwind, 향후 조건부 자원에 유리 | 실행 순서가 등록 역순이라 고정 3단계에는 인지 비용이 큼 | 예비안 |
| 명명된 coordinator + 중첩 `try/finally` | 고정 순서를 위→아래로 읽을 수 있고 예외 전파가 명시적 | 중첩 구조를 평평한 연속 `await`로 단순화하면 다시 회귀함 | **채택** |
| 각 cleanup을 `asyncio.shield()`로 감쌈 | 내부 작업이 외부 취소와 분리됨 | shield를 await하는 바깥 태스크는 즉시 취소될 수 있어, 내부 task를 별도로 보관·회수하지 않으면 완료 보장이 없음 | 단독 사용 금지 |
| `except BaseException: pass` | 겉보기에는 cleanup 지속 | `CancelledError`, `KeyboardInterrupt`, `SystemExit`를 영구 억제함 | 금지 |

채택 구조는 `_shutdown_application_resources(app)`라는 고정 순서 coordinator를 둔다. 각 단계는
중첩 `try/finally` 또는 그와 동등한 unwind 구조로 연결한다. `CancelledError`를 직접 삼키지 않으며,
첫 단계에서 들어온 취소는 후속 정리와 `app.state.resources = None` 수행 후 자동 재전파되게 한다.

향후 Redis/API client처럼 조건부로 획득되는 자원이 추가되면 해당 자원은 획득 성공 직후
`AsyncExitStack`에 등록하고 ADR을 다시 평가한다.

### 4.2 logging listener 소유권

| 대안 | 평가 |
|---|---|
| lifespan에서 stop 유지 | Uvicorn 최종 로그보다 먼저 listener가 종료되므로 기각 |
| `main.py`의 `uvicorn.run()` 뒤에서만 stop | `uvicorn main:app` CLI 경로에는 적용되지 않아 기각 |
| process logging subsystem + idempotent `atexit` stop | CLI, 직접 실행, 일반 정상 프로세스 종료를 함께 포괄하므로 **채택** |

`app.utils.logs.setup`이 listener 생성과 process 종료를 함께 소유한다. `atexit` handler는 동기
`stop_log_listener()`를 호출하며, 수동 테스트와 worker hook에서 같은 idempotent API를 재사용한다.
SIGKILL은 비범위다. Celery prefork 자식은 기존 `restart_log_listener()` 후 자기 process의 종료
handler가 현재 전역 listener를 정리하게 한다. 프로젝트가 지원하는 표준 실행 경로는
`main.py:run_server()` 하나로 모으고 비패키지 정책(`tool.uv.package = false`)에 맞춰
`uv run python main.py`가 이 함수를 사용하게 한다. bare `uvicorn main:app`은 project log config를
주입할 수 없으므로 표준 실행 명령에서 제외하고 문서에 비권장 경로로 명시한다.

---

## 5. 목표 구조와 계약

### 5.1 목표 수명주기

```text
process 시작
  └─ logging configure/start + process-exit stop 등록
      └─ FastAPI lifespan startup
          ├─ app.state.resources 설정
          ├─ 모델 import/DB 준비
          └─ yield
              └─ FastAPI lifespan shutdown
                  1. background task drain
                  2. DB writer/readers/background engine dispose
                  3. app.state.resources = None
                  4. "요청 처리 자원 해제 완료" 기록
      └─ Uvicorn lifespan/shutdown 최종 로그
  └─ process 종료 시 logging queue flush/listener stop
```

### 5.2 오류 전파 계약

| 상황 | 필수 동작 |
|---|---|
| cleanup 일반 `Exception` | 해당 자원 실패 기록, 다음 자원 계속, lifespan 원인 예외는 보존 |
| 자원 timeout | 자원명·예산 기록, 다음 자원 계속 |
| lifespan `CancelledError` | 모든 후속 cleanup 시도, 상태 참조 제거, 마지막에 취소 재전파 |
| cleanup 중 추가 취소 | 아직 실행하지 않은 필수 finally가 수행되도록 unwind, 취소 억제 금지 |
| DB engine 일부 실패 | 나머지 engine 전부 시도, 오류 집계 후 상위 cleanup logger에 한 번 보고 |
| listener stop 실패 | 전역 참조 유지, 직접 stderr fallback으로 실패 기록, 재시도 가능 |

### 5.3 로그 메시지 계약

- lifespan 시작: `[shutdown] 애플리케이션 요청 처리 자원 해제 시작`
- lifespan 성공: `[shutdown] 애플리케이션 요청 처리 자원 해제 완료`
- process logging stop 시작/성공/실패는 queue를 거치지 않는 안전한 최종 sink를 사용한다.
- listener stop 전에는 전체 process 자원 “완료”라고 기록하지 않는다.

---

## 6. 작업 계획

모든 구현 작업은 실패 테스트를 먼저 작성하는 TDD 순서로 수행한다.

### Wave 1 — Critical 회귀 재현

#### Task 1. lifespan 관리자 취소 회귀 테스트 추가

- **목적:** RL-001을 기존 테스트의 false green에서 분리한다.
- **read_first:**
  - `app/core/resources.py`
  - `tests/core/test_resources.py`
  - `docs/2026-08-25/shutdown-sequence-analysis.md`
- **files_modified:** `tests/core/test_resources.py`
- **작업:**
  1. 가짜 drain이 `asyncio.Event`에서 대기하도록 구성한다.
  2. `manage_application_resources()`를 별도 task로 실행한다.
  3. drain 진입을 확인한 뒤 manager task 자체를 `cancel()`한다.
  4. `CancelledError` 재전파와 함께 dispose 호출, 상태 참조 제거를 검증한다.
  5. process logging 소유권 이전 전 단계라면 listener stop 호출도 임시 기준선으로 검증하고,
     Task 3 완료 후에는 “lifespan에서 stop하지 않음”으로 기대값을 갱신한다.
- **acceptance_criteria:**
  - 수정 전 새 테스트가 실패한다.
  - 실패 메시지에 누락된 `dispose` 또는 stale `app.state.resources`가 드러난다.
  - 자식 background task 취소 테스트와 이름·목적이 구분된다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\core\test_resources.py -k "manager and cancel"`
- **dependencies:** 없음

### Wave 2 — Critical 회귀 수정

#### Task 2. 취소 안전한 shutdown coordinator 구현

- **목적:** 고정 순서의 가독성을 유지하면서 BaseException-safe unwind를 복원한다.
- **read_first:**
  - `app/core/resources.py`
  - `tests/core/test_resources.py`
- **files_modified:** `app/core/resources.py`, `tests/core/test_resources.py`
- **작업:**
  1. `_shutdown_application_resources(app)`를 추가한다.
  2. drain → dispose → `app.state.resources = None`을 중첩 `try/finally`로 연결한다.
  3. `_run_cleanup()`은 timeout과 일반 `Exception`만 기록·격리하고 `CancelledError`는 억제하지 않는다.
  4. `manage_application_resources()`의 `finally`는 coordinator 한 번만 호출한다.
  5. 모듈 및 `_run_cleanup()` 독스트링에 일반 실패와 취소의 서로 다른 계약을 명시한다.
- **acceptance_criteria:**
  - manager가 drain 또는 dispose 중 취소돼도 뒤 단계와 상태 제거가 실행된다.
  - 호출자는 최종적으로 `CancelledError`를 받는다.
  - 정상 종료 순서는 drain → dispose → state clear이다.
  - startup 실패 시에도 생성된 자원 정리를 시도한다.
  - `except BaseException: pass`와 무회수 `asyncio.shield()`가 없다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\core\test_resources.py`
  - `.\.venv\Scripts\python.exe -m ruff check app\core\resources.py tests\core\test_resources.py`
  - `.\.venv\Scripts\python.exe -m mypy app\core\resources.py`
- **dependencies:** Task 1

### Wave 3 — process logging 소유권 이전

#### Task 3. logging listener 소유권을 process로 이전

- **목적:** Uvicorn 및 startup 실패의 마지막 로그까지 같은 queue에서 소비한다.
- **read_first:**
  - `app/core/resources.py`
  - `app/utils/logs/setup.py`
  - `app/utils/logs/__init__.py`
  - `main.py`
  - `README.md`의 Uvicorn 실행 명령
  - `app/celery/lifecycle.py`
  - `tests/utils/test_logs.py`
- **files_modified:**
  - `app/core/resources.py`
  - `app/utils/logs/setup.py`
  - `app/utils/logs/__init__.py`
  - `main.py`
  - `README.md`
  - `tests/core/test_resources.py`
  - `tests/utils/test_logs.py`
- **작업:**
  1. lifespan 종료 후 listener가 살아 있어야 한다는 테스트와 `python main.py`가
     `run_server()` 및 project log config를 사용한다는 테스트를 먼저 추가하고 red를 확인한다.
  2. lifespan에서 `start_log_listener()` handle 저장과 `_stop_log_listener()` 호출을 제거한다.
  3. `ApplicationResources.log_listener`와 사용되지 않는 `_extra`를 제거한다.
  4. logging 구성 시 process당 한 번만 동기 `stop_log_listener()`를 `atexit`에 등록한다.
  5. start/stop/restart 전역 상태를 `threading.RLock`으로 보호하고 idempotent하게 만든다.
  6. `configure_logging(force=True)`와 Celery fork 후 restart가 중복 listener를 만들지 않게 한다.
  7. `main.py`의 현재 `uvicorn.run()` 블록을
     `run_server(app_import: str = "main:app")`로 추출한다. README 표준 명령은
     `uv run python main.py`로 바꾸고 bare `uvicorn main:app`은 project queue lifecycle을 우회하는
     비권장 명령이라고 명시한다. `tool.uv.package = false`는 변경하지 않는다.
  8. `run_server()`가 `setup_uvicorn_logging()` 결과를 `uvicorn.run(log_config=...)`에 전달하며,
     Uvicorn logger 3종이 앱과 같은 handler instance를 사용한다는 계약 테스트를 추가한다.
  9. queue를 통하지 않고 `sys.__stderr__`에 쓰는 `_write_listener_lifecycle_status()`를 추가해
     process stop 시작·성공·실패를 기록한다.
  10. lifespan 완료 로그를 “요청 처리 자원 해제 완료”로 좁힌다.
- **acceptance_criteria:**
  - FastAPI lifespan 종료 뒤에도 listener가 살아 있다.
  - process stop API를 한 번 또는 여러 번 호출해도 listener thread는 하나만 종료된다.
  - `uv run python main.py`가 `run_server()`를 사용하고 `tool.uv.package = false`를 유지한다.
  - `run_server()`의 Uvicorn logger가 앱과 같은 queue handler,
    `StaticAppFilter(appname="uvicorn")`, logger 3종 계약을 사용한다.
  - README의 표준 실행 예시에 bare `uvicorn main:app`이 남아 있지 않다.
  - process stop 시작·성공·실패 메시지는 queue가 아닌 `sys.__stderr__`에서 관측된다.
  - `ApplicationResources`에 실제로 소유하지 않는 listener 필드가 없다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\utils\test_logs.py tests\core\test_resources.py`
- **dependencies:** Task 2

### Wave 4 — 자원별 실패 격리와 logging stop 상태 기계

Task 4, Task 5, Task 6은 Task 3 완료 후 서로 다른 파일을 소유하며 병렬 수행할 수 있다.

#### Task 4. DB engine 전체 dispose 시도와 오류 집계

- **목적:** writer 또는 reader 하나의 실패가 다른 pool 정리를 중단하지 않게 한다.
- **read_first:**
  - `app/core/db/session.py`
  - `app/core/resources.py`
  - `app/celery/lifecycle.py`
  - `tests/core/test_resources.py`
  - `tests/test_celery_bridge.py`
- **files_modified:**
  - `app/core/db/session.py`
  - `app/core/resources.py`
  - `app/celery/lifecycle.py`
  - `tests/core/test_db_engine_disposal.py` (신규)
  - `tests/core/test_resources.py`
  - `tests/test_celery_bridge.py`
- **작업:**
  1. writer 실패, 중간 reader 실패, engine timeout, dispose 중 외부 취소를 재현하는 테스트를
     먼저 추가하고 red를 확인한다.
  2. `dispose_engine(*, deadline: float)`로 계약을 바꾼다. FastAPI는
     `asyncio.get_running_loop().time() + DB_DISPOSE_TIMEOUT_SECONDS`, Celery는 worker loop의
     `loop.time() + timeout`으로 deadline을 한 번만 계산해 전달한다.
  3. writer, 각 reader, background engine을 이름이 있는 ordered list로 만든다.
  4. 각 engine 시작 시 `remaining_total = deadline - loop.time()`과 `remaining_count`를 계산하고,
     `slice_timeout = max(0, remaining_total) / remaining_count`를 적용한다. 빠르게 끝난 engine의
     남은 시간은 후속 engine에 자동 재분배한다.
  5. 일반 `Exception`/engine별 `TimeoutError`는 engine 이름과 함께 수집하고 다음 engine을 계속한다.
  6. 외부 `CancelledError`도 첫 인스턴스를 보존한 채 아직 시작하지 않은 engine을 각자의 남은
     slice 안에서 계속 시도한다. 모든 시도 후 취소가 있으면 일반 오류보다 우선해 원래 취소를
     재전파하고, 일반 오류는 그 전에 로그로 남긴다.
  7. 취소가 없고 일반 오류만 있으면 모든 시도 후 `ExceptionGroup`을 올린다.
  8. `_dispose_db_engines()`에서 중복된 바깥 `asyncio.timeout(10)`을 제거해 단일 absolute deadline만
     총예산의 원천이 되게 한다.
  9. Celery의 `asyncio.wait_for(dispose_engine(), timeout)`를 제거하고
     `dispose_engine(deadline=loop.time() + timeout)`를 `run_until_complete()`로 실행한다. FastAPI와
     Celery 모두 동일한 내부 deadline 알고리즘을 사용하며 외부 timeout 중첩을 두지 않는다.
- **acceptance_criteria:**
  - writer 실패 뒤 모든 reader와 background dispose가 호출된다.
  - 중간 reader 실패 뒤 후속 reader와 background dispose가 호출된다.
  - 가변 reader 수에서도 관측된 전체 소요 시간이 10초 예산과 작은 scheduler 허용 오차를 넘지 않는다.
  - 외부 취소와 일반 오류가 함께 있으면 모든 engine을 bounded 시도한 뒤 원래 `CancelledError`가
    우선 재전파된다.
  - 취소가 없을 때만 실패 engine 이름을 포함한 `ExceptionGroup`이 상위로 전달된다.
  - Celery의 10초 cleanup 예산도 같은 absolute deadline으로 제한되고 dispose 실패 뒤 loop close는
    기존처럼 실행된다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\core\test_db_engine_disposal.py`
  - `.\.venv\Scripts\python.exe -m pytest -q tests\test_celery_bridge.py tests\core\test_resources.py`
- **dependencies:** Task 3

#### Task 5. BackgroundTaskRunner 예외 회수

- **목적:** 완료 task의 `Task exception was never retrieved` 경고를 제거한다.
- **read_first:**
  - `app/core/middlewares/background_tasks.py`
  - `tests/core/test_background_tasks.py`
- **files_modified:**
  - `app/core/middlewares/background_tasks.py`
  - `tests/core/test_background_tasks.py`
- **작업:**
  1. 실패 coroutine과 loop exception handler를 사용해 미회수 예외를 재현하고 red를 확인한다.
  2. done callback을 명명된 메서드로 분리한다.
  3. set 제거 후 `task.cancelled()`를 확인한다.
  4. 취소되지 않은 task는 `task.exception()`을 호출해 예외를 회수하고 명시적으로 로깅한다.
  5. 정상 완료·취소는 error로 기록하지 않는다.
- **acceptance_criteria:**
  - 실패 coroutine의 예외가 정확히 한 번 기록된다.
  - loop exception handler에 `Task exception was never retrieved`가 전달되지 않는다.
  - 정상·취소·timeout drain 테스트가 모두 통과한다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\core\test_background_tasks.py`
- **dependencies:** Task 3

#### Task 6. bounded queue 포화 종료를 재시도 가능하게 구현

- **목적:** sentinel 삽입 실패 시 listener thread와 전역 handle을 잃지 않게 한다.
- **read_first:**
  - `app/utils/logs/setup.py`
  - `app/utils/logs/queue_handler.py`
  - Python `QueueListener.enqueue_sentinel()` 공식 문서
  - `tests/utils/test_logs.py`
- **files_modified:**
  - `app/utils/logs/setup.py`
  - `tests/utils/test_logs.py`
- **작업:**
  1. queue 포화, 느리거나 정지한 sink, 첫 stop timeout 뒤 재시도, 동시 start/stop 테스트를 먼저
     추가하고 red를 확인한다.
  2. `RUNNING`, `STOPPING`, `STOPPED` 상태와 `sentinel_enqueued` 여부를 가진 전용
     `BoundedQueueListener`를 추가한다.
  3. 하나의 monotonic deadline을 sentinel enqueue와 thread join이 공유하게 한다. enqueue는
     `queue.put(sentinel, timeout=remaining)`을 사용하고 join도 `thread.join(remaining)`을 사용한다.
  4. sentinel enqueue 전에 timeout이면 `RUNNING`과 기존 handle을 유지한다. enqueue 뒤 join timeout이면
     `STOPPING`, `sentinel_enqueued=True`, 기존 handle을 유지한다.
  5. `STOPPING` 재시도는 sentinel을 다시 넣지 않고 기존 thread join만 계속한다.
  6. thread 종료 확인 뒤에만 `STOPPED`로 전이하고 `_listener = None`으로 만든다.
  7. `STOPPING` 동안 start 요청은 새 listener를 만들지 않고 기존 handle을 반환한다.
  8. 실패 로그는 Task 3의 직접 stderr lifecycle sink로 남긴다.
  9. `configure_logging(force=True)`는 기존 listener의 stop이 완전히 성공한 경우에만 `dictConfig()`와
     새 handler 설치를 진행한다. stop timeout 또는 `STOPPING`이면 재구성을 중단하고 기존 root
     handler·queue·listener 결합을 보존한다.
  10. stop 재시도 성공 뒤 force reconfiguration을 다시 호출하면 새 handler와 새 listener가 같은
      queue를 공유하는지 테스트한다.
- **acceptance_criteria:**
  - queue 포화 첫 stop 실패 뒤 `_listener`가 기존 인스턴스를 유지한다.
  - sentinel enqueue 뒤 join timeout 재시도에서 sentinel이 중복 삽입되지 않는다.
  - 느린 sink에서도 stop 전체 호출이 설정 deadline 안에 반환한다.
  - 재시도 성공 뒤 listener thread가 종료되고 state가 `STOPPED`, `_listener is None`이다.
  - stop/start 경쟁 테스트에서 동시에 두 listener가 살아 있지 않다.
  - `STOPPING` 중 force reconfiguration이 실패해도 root handler queue와 기존 listener queue의
    identity가 같다.
  - 테스트 종료 후 daemon 여부와 무관하게 기록한 listener thread identity가 살아 있지 않다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\utils\test_logs.py -k "listener or queue"`
- **dependencies:** Task 3

### Wave 5 — 실제 process 검증

#### Task 7. Uvicorn 실제 종료·startup 실패 통합 테스트

- **목적:** lifespan 직접 호출이 아닌 실제 server process의 로그 순서를 증명한다.
- **read_first:**
  - `main.py`
  - `app/utils/logs/setup.py`
  - `compose.test.yaml` 및 테스트 환경 문서(존재 시)
  - `docs/2026-08-25/verification-report.md`
- **files_modified:**
  - `tests/integration/test_uvicorn_lifecycle.py` (신규)
  - `tests/integration/uvicorn_startup_failure_app.py` (신규)
- **작업:**
  1. 사용 가능한 임시 포트를 할당하고 두 subprocess 모두 부모 pytest 환경을 그대로 상속하지
     않도록 `env`를 복사한 뒤 `DEBUG=false`, `ENV=test`, `SERVER_HOST=127.0.0.1`,
     `SERVER_PORT=<allocated-port>`를 명시적으로 덮어쓴다.
  2. 위 환경으로 `.\.venv\Scripts\python.exe main.py` subprocess를 시작하고 project 로그 포맷과
     `[app=uvicorn]` 라벨을 확인한다. `DEBUG=false`이므로 `reload=False`이며 startup DB 자동 생성은
     실행하지 않는 것을 전제로 한다.
  3. Windows에서는 `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP`으로 시작한 뒤
     `process.send_signal(signal.CTRL_BREAK_EVENT)`를 정상 종료 신호로 사용한다. POSIX에서는
     `SIGTERM`을 사용한다. `terminate()`/`kill()`은 timeout 시 fixture 정리 fallback으로만 사용한다.
  4. subprocess는 `stderr=subprocess.STDOUT`으로 단일 pipe를 사용한다. 병합된 stream에서 lifespan
     요청 처리 자원 완료 → Uvicorn shutdown 완료 → 직접 stderr의 process logging stop 완료 순서를
     검증한다.
  5. `tests.integration.uvicorn_startup_failure_app:app`에 lifespan 진입 시
     `RuntimeError("intentional startup failure RL-002")`를 올리는 FastAPI app을 만든다.
     `.\.venv\Scripts\python.exe -c "from main import run_server; run_server('tests.integration.uvicorn_startup_failure_app:app')"`
     로 실행해 정상 server와 동일한 `run_server()`/`setup_uvicorn_logging()` 및 1번의 명시적 환경을
     사용한다.
  6. 모든 subprocess에 강제 종료 fallback과 제한시간을 둬 CI hang을 방지한다.
- **acceptance_criteria:**
  - 정상 종료에서 project 포맷의 `[app=uvicorn]`과 `Application shutdown complete` 또는 사용
    Uvicorn 버전의 동등 로그가 함께 관측돼 공유 queue 경로를 증명한다.
  - startup 실패에서도 project 포맷의 `[app=uvicorn]`, `RuntimeError`,
    `intentional startup failure RL-002`, process listener stop 완료가 단일 stream에서 관측된다.
  - 두 subprocess 출력에 Uvicorn `Started reloader process`가 없고 server process는 하나만 시작된다.
  - `DEBUG=false` 로그와 운영 정책의 DB 자동 생성 건너뜀 로그가 관측되며 MySQL 없이 readiness 또는
    의도한 startup failure 지점까지 도달한다.
  - Windows 정상 경로는 `CTRL_BREAK_EVENT`, POSIX 정상 경로는 `SIGTERM`이며 강제 종료 fallback과
    테스트 결과가 구분된다.
  - 테스트 후 child process와 listener thread가 남지 않는다.
  - Windows와 POSIX 차이가 fixture 내부로 격리된다.
- **verification:**
  - `.\.venv\Scripts\python.exe -m pytest -q tests\integration\test_uvicorn_lifecycle.py`
- **dependencies:** Task 3, Task 4, Task 5, Task 6

### Wave 6 — 문서와 검증 게이트 수렴

#### Task 8. 문서·CRP·검증 게이트 갱신

- **목적:** 코드, ADR, 결함 ledger, 검증 결과를 같은 사실로 수렴시킨다.
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
  - `docs/orm-raw-repository/2026-08-13/workflow-guide.md`
  - `scripts/review_gate.py`
  - `conftest.py` (신규)
  - `tests/integration/conftest.py`
- **작업:**
  1. RL-001~007을 “2026-08-25 review에서 발견”한 이력으로 ledger에 추가하고, 각 항목은 해당
     회귀 테스트와 구현 근거가 생긴 뒤에만 closed로 기록한다.
  2. ADR-016을 폐기하지 말고 취소 안전성 누락과 보완 결정을 후속 ADR로 추가한다.
  3. `refactoring-report.md`의 “잃음 없음”과 분석 문서의 “의미 동일”을 사실에 맞게 정정한다.
  4. `verification-report.md`는 전체 테스트 재실행 전 `CONVERGED`로 표시하지 않는다.
  5. `scripts/review_gate.py`에 파일·문맥별 금지 문구 검사를 추가한다. 역사 설명이 아닌 현재 계약에서
     `잃음 없음`, `평문 try/finally와 의미 동일`, 근거 없는 `CONVERGED`를 발견하면 non-zero로 종료한다.
  6. 초기 pytest parsing에 로드되는 루트 `conftest.py`에 `--mysql-required` option을 추가한다.
     `tests/integration/conftest.py`의 MySQL fixture는 이 option이 있고 DB가 도달 불가능하면 skip 대신
     session 실패로 처리한다.
  7. 정적 gate에 manager 취소 테스트와 process lifecycle 테스트 파일 존재·실행 여부를 포함한다.
  8. 실제 실행한 명령, 환경, passed/skipped 수만 기록한다.
- **acceptance_criteria:**
  - RL-001~007 각각에 코드 또는 검증 근거가 연결된다.
  - 문서 어디에도 평문 연속 `await`와 `AsyncExitStack`의 취소 의미가 동일하다는 주장이 없다.
  - 실행하지 않은 SIGTERM/Windows 경로를 실행한 것으로 기록하지 않는다.
  - `CONVERGED`는 Definition of Done을 모두 충족한 뒤에만 복원된다.
  - `--mysql-required` 실행에서 MySQL 부재는 skip이 아니라 실패다.
- **verification:**
  - executor는 아래 PowerShell 블록처럼 compose teardown을 `finally`/CI `always()`에서 보장한다.

```powershell
try {
    docker compose -f compose.test.yaml up -d --wait
    if ($LASTEXITCODE -ne 0) { throw "MySQL test container startup failed" }

    .\.venv\Scripts\python.exe -m pytest -q tests\integration -m mysql --mysql-required
    if ($LASTEXITCODE -ne 0) { throw "required MySQL tests failed" }

    .\.venv\Scripts\python.exe scripts\review_gate.py
    if ($LASTEXITCODE -ne 0) { throw "review gate failed" }
}
finally {
    docker compose -f compose.test.yaml down -v
}
```
- **dependencies:** Task 1~7

---

## 7. 테스트 매트릭스

| 영역 | 정상 | 일반 실패 | timeout | 외부 취소 | 재진입/경쟁 | 실제 process |
|---|---:|---:|---:|---:|---:|---:|
| lifespan coordinator | 필수 | 필수 | 필수 | **필수** | 필수 | Task 7 |
| background drain | 기존 | 기존/보강 | 기존 | 기존 자식 취소 + manager 취소 | 필수 | 간접 |
| DB dispose | 필수 | engine별 필수 | engine별 필수 | 필수 | 선택 | 간접 |
| logging listener | 필수 | 필수 | sentinel timeout 필수 | 해당 없음 | **필수** | **필수** |
| startup failure | 기존 | **필수** | 선택 | 선택 | 필수 | **필수** |

전체 검증 순서:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\core\test_resources.py
.\.venv\Scripts\python.exe -m pytest -q tests\core\test_background_tasks.py tests\utils\test_logs.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\review_gate.py
```

MySQL 통합 테스트는 `compose.test.yaml`의 전용 포트와 healthcheck를 사용하고, 결과에서 skipped 수를
반드시 확인한다.

---

## 8. 요구사항 추적

| 요구/품질 속성 | 작업 | 증명 |
|---|---|---|
| 종료 순서 명료성 | Task 2 | 정상 순서 단위 테스트 + coordinator 코드 |
| 취소 안전성 | Task 1, 2, 4 | manager/DB dispose 취소 테스트 |
| 실패 격리 | Task 2, 4, 5, 6 | 실패·timeout·포화 테스트 |
| 로그 완전성 | Task 3, 6, 7 | Uvicorn 정상 종료/startup 실패 subprocess 로그 |
| 상태 참조 무효화 | Task 1, 2 | 모든 종료 유형에서 `app.state.resources is None` |
| 개발자 이해 용이성 | Task 2, 8 | 이름 있는 coordinator, 계약 독스트링, 최신 workflow 예시 |
| 문서 신뢰성 | Task 8 | CRP ledger와 실제 명령 결과 연결 |

---

## 9. 배포·관측·롤백 계획

### 배포 전

1. Task 1의 테스트가 기존 구현에서 실패하는지 확인한다.
2. Wave별 테스트와 전체 gate를 모두 통과한다.
3. 실제 Uvicorn process에서 shutdown/startup-failure 로그를 수집한다.
4. multi-worker 사용 시 worker별 listener thread가 하나인지 확인한다.

### 관측 항목

- shutdown 단계별 소요 시간과 timeout 횟수
- DB engine별 dispose 실패 수
- logging queue drop 수와 listener stop retry 수
- background task 실패·취소 수
- shutdown 후 남은 listener thread·child process 유무

### 롤백

- Wave 1 실패: production 코드는 건드리지 않고 실패 재현 테스트와 재현 로그를 보존한다.
- Wave 2 실패: coordinator 구현을 원복하고 `AsyncExitStack` 복원을 대체 구현으로 적용하되 Task 1의
  취소 회귀 테스트는 유지한다.
- Wave 3 실패: process-level logging 소유권 변경만 원복하고 RL-001 수정은 유지한다.
- Wave 4 실패: DB, background task, listener state machine 변경을 각각 독립적으로 원복한다.
- Wave 5 실패: process 통합 테스트와 fixture만 격리해 원인을 분석하며 강제 종료 결과를 정상 종료
  근거로 사용하지 않는다.
- Wave 6 실패: false-positive gate만 원복하고 RL-001~007의 발견 이력과 검증 로그는 보존한다.
- 데이터와 DB 스키마를 변경하지 않으므로 migration rollback은 없다.
- 롤백 후에도 새 회귀 테스트는 삭제하지 않고 기대 계약 변경이 승인된 경우에만 수정한다.

---

## 10. 주요 위험과 대응

| 위험 | 대응 |
|---|---|
| `atexit`가 강제 종료에서 실행되지 않음 | SIGKILL은 비범위로 명시하고 정상 SIGTERM 유예 시간을 확보 |
| logging stop lock과 listener thread의 교착 | lock 안에서는 상태 전이만 하고 장시간 join 범위를 최소화, timeout 테스트 추가 |
| 취소를 잡은 뒤 재전파하지 않음 | manager 취소 테스트에서 호출자가 `CancelledError`를 받는지 강제 |
| process 통합 테스트의 CI hang | readiness/종료/kill 각각에 제한시간과 강제 정리 fixture 적용 |
| ExceptionGroup 로그가 읽기 어려움 | engine 이름을 각 예외에 포함하고 요약 로그 + 상세 traceback을 분리 |
| 문서부터 `CONVERGED`로 닫힘 | Task 8을 마지막 wave로 고정하고 전체 gate 결과를 선행 조건으로 둠 |

---

## 11. Definition of Done

- [ ] lifespan manager가 drain 또는 dispose 중 취소돼도 필수 후속 cleanup을 전부 시도한다.
- [ ] cleanup 후 원래 `CancelledError`가 호출자에게 재전파된다.
- [ ] 정상·startup 실패·timeout·취소에서 `app.state.resources is None`이다.
- [ ] logging listener는 lifespan보다 오래 살아 Uvicorn 최종 로그와 startup 실패 traceback을 소비한다.
- [ ] bounded queue 포화 stop 실패가 listener handle 또는 thread 누수로 이어지지 않는다.
- [ ] 모든 DB engine이 개별 실패와 무관하게 dispose 시도된다.
- [ ] background task 예외가 회수·기록되고 event loop 미회수 경고가 없다.
- [ ] 단위·정적·전체·MySQL·process lifecycle 검증 결과가 기록된다.
- [ ] 문서와 CRP ledger가 구현 및 실제 검증 결과와 일치한다.
- [ ] 공개 API와 DB 스키마 diff가 0이다.

---

## 12. 구현 완료 후 산출물

1. 수정 코드와 회귀 테스트
2. 실제 Uvicorn 종료/startup 실패 검증 로그
3. 후속 ADR 및 CRP finding close 근거
4. 갱신된 `refactoring-report.md`, `shutdown-sequence-analysis.md`, `verification-report.md`
5. 전체 검증 명령과 passed/skipped 수가 포함된 최종 검증 보고서
