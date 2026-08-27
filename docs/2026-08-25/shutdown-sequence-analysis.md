# 애플리케이션 종료 절차 분석

| 항목 | 값 |
|---|---|
| 작성일 | 2026-08-25 |
| 대상 | `main.py` lifespan · `app/core/resources.py` |
| 계기 | "lifespan 의 `yield` 이후에 자원 해제 코드가 없는 것 같다" |
| 결론 | 해제는 정상 동작한다. 결함은 **동작이 아니라 읽는 비용**에 있었다 |
| 연결 | `docs/crp/groups/orm-raw-repository/` Round 11 · ADR-016 · F-026 |

---

## 1. 최초 관찰과 그 정당성

`main.py` 의 lifespan 은 이렇게 생겼다.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with manage_application_resources(app):
        yield
```

`yield` 뒤에 아무것도 없다. "서버가 종료될 때 DB 커넥션을 닫는 코드가 어디에도 없다"는
관찰은 **이 파일만 보는 사람에게는 옳다.**

실제로는 동작한다. `yield` 는 함수의 끝이 아니라 **중단점**이고, 종료 시 FastAPI 가
제너레이터를 재개하면 `async with` 블록을 빠져나가면서 `manage_application_resources` 의
`__aexit__` 가 호출되기 때문이다. 자원 해제는 전부 그 안에 있다.

그러나 그것을 확인하려면 다른 파일로 건너가야 했고, 건너간 곳에서는
`AsyncExitStack` 의 **등록 역순 규칙을 머릿속에서 뒤집어야** 했다. 이 문서가 기록하는
것은 그 비용이다.

---

## 2. 종료 호출 사슬 (실측)

종료 신호 수신 시점부터, 최초 호출 함수 기준 실행 순서다.

| # | 파일명:함수명 | 하는 일 |
|---|---|---|
| 0 | *(uvicorn)* `uvicorn/server.py:Server.handle_exit` | 시그널 수신 → 신규 요청 수신 중단 → lifespan shutdown 발신 |
| 1 | `main.py:lifespan` | `yield` 지점에서 재개 → `async with` 블록 탈출 |
| 2 | `app/core/resources.py:manage_application_resources` | `finally` 진입 |
| 3 | `app/core/resources.py:_drain_background_tasks` | 1단계 (예산 5.0s) |
| 4 | `app/core/resources.py:_run_cleanup` | `asyncio.timeout(5.0)` + 실패 격리 |
| 5 | `app/core/middlewares/background_tasks.py:BackgroundTaskRunner.drain` | 4.0s 대기 → `cancel()` → `gather()` 회수 |
| 6 | `app/core/resources.py:_dispose_db_engines` | 2단계 (예산 10.0s) |
| 7 | `app/core/resources.py:_run_cleanup` | `asyncio.timeout(10.0)` |
| 8 | `app/core/db/session.py:dispose_engine` | writer → read replica 전체 → background engine 순 `dispose()` |
| 9 | `app/core/resources.py:_stop_log_listener` | 3단계 (예산 5.0s) |
| 10 | `app/core/resources.py:_run_cleanup` | `asyncio.timeout(5.0)` |
| 11 | `app/utils/logs/setup.py:stop_log_listener_async` | `asyncio.to_thread()` 로 event loop 밖에 위임 |
| 12 | `app/utils/logs/setup.py:stop_log_listener` | (별도 스레드·동기) `QueueListener.stop()` — flush 후 join |

`app.state.resources = None` 과 종료 완료 로그는 11번 **직전**에 실행된다(§4 참조).

### 실측 로그

실제 `main.app` 을 기동·종료해 관측한 것이다(코드 읽기가 아니라 실행 결과).

```text
[shutdown] 애플리케이션 자원 해제 시작
[shutdown] background task 정리 완료 (0.0ms)
[dispose_engine] Disposing database engines...
[dispose_engine] Main engine disposed
[dispose_engine] Background engine disposed - ALL DONE
[shutdown] DB engine 정리 완료 (0.4ms)
[shutdown] 애플리케이션 자원 해제 완료
```

---

## 3. 왜 이 순서인가

순서를 바꾸면 각각 다음이 깨진다.

| 순서 | 어기면 |
|---|---|
| drain 이 dispose 보다 먼저 | 태스크가 세션을 쥔 채 엔진이 닫혀 커넥션이 강제로 끊긴다 |
| dispose 가 listener stop 보다 먼저 | 종료 과정에서 나는 오류가 어디에도 기록되지 않는다 |
| drain 의 내부 대기(4.0s) < 바깥 guard(5.0s) | 취소된 태스크의 `finally`(세션 rollback·close)가 실행되지 못한다 — ledger **F-001** 이 이 결함이었다 |

`_run_cleanup()` 이 예외와 timeout 을 **삼키는 것**도 순서 보장의 일부다. 하나가 실패했다고
뒤따르는 정리를 건너뛰면 자원이 샌다.

### 자원별 예산

| 단계 | 예산 | 근거 |
|---|---|---|
| background drain | 5.0s (내부 대기 4.0s = `DRAIN_WAIT_RATIO` 0.8) | 확정 정책 6 |
| DB dispose | 10.0s | 확정 정책 6 |
| logging drain | 5.0s | 확정 정책 6 |
| **합계** | **20.0s** = `SHUTDOWN_TOTAL_TIMEOUT_SECONDS` | 순차 실행이라 합이 곧 실측 상한 |

전체 상한은 런타임 guard 가 아니라 **산술**로 지켜진다. 누가 개별 예산을 올리면
`test_shutdown_timeout_budget_fits_total` 이 실패한다.

---

## 4. `AsyncExitStack` 평가 — 왜 걷어냈는가

변경 전 구조는 이랬다.

```python
async with AsyncExitStack() as cleanup:
    cleanup.push_async_callback(_stop_log_listener)       # 3번째로 실행
    cleanup.push_async_callback(_dispose_db_engines)      # 2번째로 실행
    cleanup.push_async_callback(_drain_background_tasks)  # 1번째로 실행

    resources.log_listener = start_log_listener()   # ← 획득은 등록 **이후**
    await _prepare_database(resources)              # ← 획득은 등록 **이후**
```

`AsyncExitStack` 의 존재 이유는 **획득과 해제를 짝지어**, 3개 중 2개만 만들어진 상태에서
실패해도 그 2개만 정확히 되돌리는 것이다. 그런데 이 코드는 콜백 3개를 자원 획득
**이전에** 한꺼번에 등록했다. 결과:

- 어디서 실패하든 **항상 3개 콜백이 전부 실행**된다 → 부분 정리가 작동한 적이 없다
- 즉 ExitStack 은 "순서 있는 콜백 리스트" 이상을 하지 않았다 — **단, 취소 경로까지 동일하지는 않았다(아래 정정)**
- 대가로 등록 순서와 실행 순서가 반대가 되어, 주석 세 줄(`# 3번째로 실행`…)로 그 간극을 메우고 있었다

"하나가 실패해도 뒤 단계를 건너뛰지 않는다"는 보장은 ExitStack 이 아니라
`_run_cleanup()` 이 제공한다. 그래서 걷어내도 **잃는 보장이 없다.**

> **정정 (2026-08-27, Round 12 / F-034).** 위 두 문장은 **일반 예외에서만 참이다.**
>
> `_run_cleanup()` 은 `except Exception` 으로 감싼다. 그런데 `asyncio.CancelledError` 는
> `Exception` 이 아니라 **`BaseException`** 이라 그 그물을 그대로 통과한다. 그래서
> 취소 경로에서는 `_run_cleanup()` 이 아무것도 보장하지 못하고, 평문 `finally` 안의
> 연속 `await` 는 첫 단계에서 취소를 맞는 순간 **뒤 단계를 통째로 건너뛴다.**
> `AsyncExitStack` 은 그 경우에도 나머지를 풀어냈다. 두 방식은 **취소에서 의미가
> 달랐고**, ADR-016 은 그 차이를 잃었다(F-028).
>
> 실측(`asyncio` 3.14, 정리 1단계에서 `CancelledError` 발생):
>
| 조립 방식 | 정리 1단계에서 `CancelledError` 발생 시 | 2단계 도달 |
|---|---|---|
| (a) `AsyncExitStack` + `push_async_callback` | `['first', 'second']` | ✅ |
| (b) 평문 `try/finally` 안의 연속 `await` | `['first']` | ❌ **건너뜀** |
| (c) 중첩 `async with` (ADR-017, 현재) | `['first', 'second']` | ✅ |
>
> 당시 이 차이를 못 본 이유는 단순하다 — **취소를 시험한 테스트가 없었다.**
> 현재 구조는 ADR-017 의 중첩 `async with` 이고, (a)의 보장과 (b)의 읽기 쉬움을 함께
> 갖는다. 회귀 테스트: `test_manager_cancellation_still_runs_remaining_cleanup`.

요구 명세와도 충돌하지 않는다 — **AR-008 수용 기준이 `try/finally` 를 첫 번째 허용
형태로 명시**한다. 이탈한 것은 development-plan §9.5 · workflow-guide §11 의 *구현 예시* 뿐이고,
그 이탈은 ADR-016 으로 등록했다.

### 재도입 조건

요구 명세는 **Redis API client 를 후속 작업으로 미뤄 둔 상태**다(requirements §4.6).
Redis 처럼 **설정이 켜졌을 때만 생성되는** 조건부 자원이 들어오면 획득 직후 등록이
필요해지고, 그때는 `try/finally` 가 흉내 낼 수 없는 값이 생긴다. 그 시점에 재평가한다.

---

## 5. 이 사슬 밖에 있는 것

- **요청별 `AsyncSession`**: lifespan 이 아니라 `get_writer_db_session` / `get_read_only_db_session`
  의존성 teardown 이 닫는다. 종료 시 in-flight 요청이 먼저 끝나므로 위 사슬보다 앞선다.
- **Celery worker 의 broker/backend·event loop**: 별도 프로세스 소유라 FastAPI lifespan 이
  닫지 않는다(AR-006). worker 는 자기 `worker_process_shutdown` 시그널에서 정리한다.
- **SIGKILL / 강제 종료**: 0번 단계가 아예 실행되지 않으므로 사슬 전체가 건너뛰어진다.
  이때 DB 커넥션은 서버 측 타임아웃으로 정리된다. 컨테이너 운영이라면 SIGTERM 유예 시간
  (Kubernetes `terminationGracePeriodSeconds`)이 전체 예산 **20초보다 길어야** 12번까지 완주한다.
