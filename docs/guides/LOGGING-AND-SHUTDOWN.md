# 로깅과 종료 — 왜 이렇게 생겼나

이 프로젝트의 로깅은 평범한 `logging` 설정처럼 보이지 않습니다. 큐가 있고, 별도 스레드가
있고, 종료할 때 하는 일이 여러 겹입니다. 그럴 만한 이유가 각각 있고, 그 이유를 모르면
**"단순하게 정리한다"** 는 선의의 수정이 로그를 조용히 없앱니다. 실제로 그런 일이 여러 번
있었습니다.

이 문서는 그 구조를 처음 보는 사람에게 설명합니다.

검토 기준: **2026-09-17 현재 작업 트리**. 설정·레벨 계산·Redis 및 DB 정리를 포함한
전체 호출 흐름은 [서버 시작·종료 HTML 안내서](./server-lifecycle-guide.html)에서 확인합니다.
신규 기능의 비동기·트랜잭션 지침은 [개발 HTML 안내서](./feature-development-guide.html)에 있습니다.

> 관련 코드: `app/utils/logs/`, `app/core/resources.py`, `main.py`
> 관련 결정: ADR-017 · ADR-018 · ADR-020 · ADR-021 · ADR-022 · ADR-023

---

## 1. 로그는 왜 큐를 거치나

보통은 `logger.info("...")` 를 부르면 **그 자리에서** 화면에 씁니다. 그런데 화면·파일에
쓰는 건 느린 I/O 라, 비동기 서버에서 그렇게 하면 그 순간 **event loop 전체가 멈춥니다.**
요청 하나가 로그를 남기는 동안 다른 모든 요청이 대기합니다.

그래서 이렇게 갈랐습니다 (NFR-009).

```
요청 처리 코드 ──put──▶ [ 로그 큐 ] ──get──▶ listener 스레드 ──▶ stdout/stderr
   (즉시 반환)                                  (느린 쓰기 담당)
```

임계값·필터를 통과한 `logger.info()`는 **출력을 큐에 위임**하고 돌아옵니다. 실제 쓰기는 뒤에서 도는
`QueueListener` 스레드가 합니다.

### 여기서 반드시 알아야 할 성질

> **`logger.info()` 가 성공했다고 그 줄이 출력된 것은 아닙니다.**
> 임계값이나 필터에서 제외될 수도 있고, 큐가 가득 차면 버려질 수도 있습니다.
> 큐에 들어갔더라도 listener가 꺼내 쓰기 전까지는 아직 출력되지 않았습니다.

`config.LogSettings`의 `get_effective_log_level(app_settings.DEBUG)`·
`get_effective_console_level(app_settings.DEBUG)`는 `build_dictconfig()`에서 호출됩니다.
`LOG_LEVEL`·`LOG_CONSOLE_LEVEL`이 없으면 DEBUG=true는 DEBUG, false는 INFO를 선택합니다.
명시값이 있으면 그 값이 우선합니다. INFO 임계값은 INFO·WARNING·ERROR·CRITICAL을 통과시킵니다.
root/handler 임계값과 필터를 함께 고려해야 하며, 시작 메시지에 전달하는 `app_settings.DEBUG`는
`%s` 표시값이지 조건문이 아닙니다. 현재 `LOG_CONSOLE_ENABLED` 필드는 console handler를
끄는 분기에 연결되어 있지 않습니다.

프로세스가 그 사이에 죽으면 **큐에 남은 줄은 영원히 사라집니다.** listener 스레드는
daemon 이라 프로세스와 함께 즉사합니다.

이 한 문장이 아래 모든 설계의 뿌리입니다.

### 큐가 가득 차면

큐는 상한이 있습니다(기본 10,000). 무한 큐는 출력이 느려질 때 메모리로 장애를 옮길 뿐입니다.

| 레벨 | 큐가 꽉 찼을 때 |
|---|---|
| DEBUG · INFO · WARNING | 버리고, 버렸다는 사실만 주기적으로 알림 |
| ERROR · CRITICAL | `sys.stderr` 로 직접 출력 (최소 포맷) |

producer 를 막는 선택지는 쓰지 않습니다. **로그 때문에 API 응답이 느려지는 것이 로그 몇 줄을
잃는 것보다 나쁩니다.**

---

## 2. 종료할 때 지켜야 하는 순서

종료 절차 자체도 로그를 남깁니다. 그래서 순서가 이렇게 고정돼 있습니다.

```
① background task 정리     ← "자원 해제 시작" 로그
② Redis client 종료
③ DB 커넥션 풀 반납        ← "DB engine 정리 완료" 로그
④ "자원 해제 완료" 로그
⑤ 여기까지의 로그가 전부 출력될 때까지 기다린다     ← ADR-023
⑥ 프로세스가 죽으면서 listener 를 멈춘다          ← ADR-018 · ADR-022
```

**①이 ②·③보다 먼저인 이유**: Redis나 DB를 쓰는 주체(background task)가 살아 있는데 client와
커넥션 풀을 닫으면 안 됩니다.

**⑥이 마지막인 이유**: listener 를 먼저 멈추면 그 뒤에 나오는 로그가 소비자 없는 큐에 갇혀
사라집니다. 실제로 이 실수가 있었고(**F-029**), 증상은 *"DB 가 꺼진 채 서버를 띄우면 오류
원인이 한 글자도 안 나온다"* 였습니다. lifespan 이 listener 를 멈춘 탓에, 그 **뒤에** uvicorn 이
남기는 traceback 이 통째로 유실됐던 것입니다.

> ⚠️ **lifespan 에서 listener 를 멈추지 마세요.** `app/core/resources.py` 는 이 이유로
> listener 를 *멈추지* 않습니다. 다만 ⑤번, 즉 **다 나갈 때까지 기다리기**는 합니다.
> 기다리기는 멈추기가 아닙니다 — listener 는 그대로 살아 있습니다.

### 순서는 어떻게 강제되나

명시적인 순서 코드가 없습니다. **중첩 컨텍스트가 순서 그 자체입니다** (ADR-017).

```python
async with _log_queue(), _database(app), _redis(app), _background_tasks():
    ...
# 정리는 자동으로 역순: background drain → Redis close → DB dispose → 로그 큐 flush
```

가장 안쪽이 가장 먼저 정리되고, 가장 바깥이 가장 나중입니다. 이 형태를 평평한 `finally`
안의 연속 `await` 로 되돌리지 마세요 — `asyncio.CancelledError` 는 `Exception` 이 아니라
`BaseException` 이라 `except Exception` 그물을 통과합니다. 연속 `await` 였을 때는 첫 단계에서
취소를 맞으면 **뒤 단계가 통째로 건너뛰어졌습니다**(**F-028**). 중첩 컨텍스트는 바깥
`__aexit__`를 시도하므로 뒤 단계의 정리 경로가 유지됩니다. 반복 취소·강제 종료나 정리
자체의 실패까지 막아 주는 것은 아닙니다.

background 5초·Redis close 5초·DB dispose 10초와 로그 flush의 개별 예산을 사용합니다.
`SHUTDOWN_TOTAL_TIMEOUT_SECONDS=20.0`을 전체 timeout으로 적용하는 코드는 없으므로
엄격한 전체 20초 보장으로 이해하면 안 됩니다.

---

## 3. 프로세스는 여러 가지 방법으로 죽는다

"프로세스가 끝날 때 큐를 비운다" 는 말처럼 간단하지 않습니다. **끝나는 방법마다 실행되는
장치가 다릅니다.**

| 끝나는 방법 | 실제 신호 | `atexit` 이 도는가 |
|---|---|---|
| 스크립트 종료 · `sys.exit()` | — | ✅ |
| 터미널 Ctrl+C | `SIGINT` | ✅ (기본 핸들러가 `KeyboardInterrupt` 를 올려 정상 종료 경로를 탄다) |
| `docker stop` · 쿠버네티스 | `SIGTERM` | ❌ **기본 동작이 즉시 종료** |
| Windows Ctrl+Break | `SIGBREAK` | ❌ **기본 동작이 즉시 종료** |
| `SIGKILL` · `kill -9` | — | ❌ (어떤 장치로도 못 막는다. 비범위) |

`SIGTERM`·`SIGBREAK` 는 파이썬이 손쓸 틈 없이 프로세스를 끝냅니다. `atexit` 만 믿으면
**운영에서 가장 흔한 종료 방법(`docker stop`)에서 로그를 잃습니다**(**F-038**).

그래서 이 두 신호에는 핸들러를 겁니다 (ADR-022).

```python
def _drain_logs_then_default(signum, frame):
    stop_log_listener()                    # 큐를 비우고 listener 정지
    signal.signal(signum, signal.SIG_DFL)  # 기본 동작으로 되돌린 뒤
    signal.raise_signal(signum)            # 같은 신호를 다시 올린다
```

**신호를 삼키지 않는 것이 핵심입니다.** 정리만 하고 살아남으면 `docker stop` 이 "종료되지 않는
컨테이너" 를 만나 결국 `SIGKILL` 까지 기다립니다. 정리한 뒤 원래 죽는 방식 그대로 죽습니다.

`SIGINT`(Ctrl+C)은 **일부러 건드리지 않습니다.** 이미 잘 동작하고, 가로채면
`KeyboardInterrupt` 를 기대하는 pytest·REPL·디버거가 조용히 달라집니다.

---

## 4. 실행 명령에 따라 달라지는 것

두 명령 모두 지원합니다. 정상 동작하고 오류·traceback 도 똑같이 나옵니다.

```bash
uv run python main.py                      # run_server() 경유
uv run uvicorn main:app --reload           # uvicorn 표준 CLI
```

차이는 **uvicorn 자신의 로그 포맷**뿐입니다.

| | `python main.py` | `uvicorn main:app` |
|---|---|---|
| uvicorn 로그 포맷 | 프로젝트 포맷 + `[app=uvicorn]` | uvicorn 기본 (`INFO:     …`) |
| 앱 로그 포맷 | 프로젝트 포맷 | 프로젝트 포맷 |
| 오류·traceback | 해당 임계값·필터 통과 시 출력 | 해당 임계값·필터 통과 시 출력 |

`python main.py` 는 `run_server()` 를 거치며 `uvicorn.run(log_config=...)` 으로 우리 설정을
넘기기 때문입니다 (ADR-020).

### 왜 앱 설정에 uvicorn 로거를 넣지 않았나

넣으면 두 경로 모두 포맷이 통일됩니다. 실제로 동작하기도 합니다 — 우리 `configure_logging()`
이 uvicorn 것보다 **나중에** 실행돼 덮어쓰기 때문입니다.

그런데 그게 문제입니다. **"왜 우리 게 이기는가" 의 답이 우리 코드 어디에도 없습니다.**
uvicorn 내부의 실행 순서에 기대는 것이고, uvicorn 이 그 순서를 바꾸면 조용히 깨지며,
리뷰어가 우리 저장소 안에서 검증할 방법이 없습니다. 반면 `log_config=` 은 uvicorn 이
문서화한 공식 파라미터라 파라미터 이름만 보고 동작을 읽을 수 있습니다.

포맷 통일이라는 이득이 그 대가만큼 크지 않다고 판단했습니다 (ADR-020).

---

## 5. `uvicorn main:app` 만 신호 핸들러가 안 통하는 이유

uvicorn 은 서버를 시작할 때 **현재 걸려 있는 신호 핸들러를 사진 찍어 두고**, 종료할 때
그 사진대로 복구한 뒤 받았던 신호를 한 번 더 쏩니다(`capture_signals()`).

문제는 **사진을 찍는 시점**입니다.

```
[python main.py]
  1. main.py 로드 → 로깅 설정 → 🔧 우리 핸들러 설치
  2. run_server() → uvicorn 시작
  3. 📷 사진 → 우리 핸들러가 찍힌다                  ✅
  ...
  4. 📷 복구 → 우리 핸들러 → 큐 비우고 죽음           ✅

[uvicorn main:app]
  1. uvicorn 이 먼저 시작
  2. 📷 사진 → 아직 우리 코드가 없다. SIG_DFL 이 찍힌다  ❌
  3. 그제서야 앱을 import → 우리 핸들러 설치 (사진은 이미 찍혔다)
  ...
  4. 📷 복구 → SIG_DFL 로 되돌아감 → 그 자리에서 즉사   ❌
```

우리가 늦게 도착할 뿐이고 순서를 바꿀 방법이 없습니다 — uvicorn 이 사진을 찍은 **다음에**
앱을 import 하도록 짜여 있기 때문입니다(**F-039**).

### 그래서 신호가 오기 전에 비운다 (ADR-023)

이 경로에서 우리 큐에 들어가는 것은 **앱 로그뿐**이고(uvicorn 로그는 자기 핸들러로 직행),
앱이 마지막으로 로그를 남기는 시점은 **lifespan 종료 절차 안**입니다. 그러니 lifespan
종료 맨 끝에서 큐를 비우면 잃을 것이 남지 않습니다.

```python
# 표준 QueueListener 는 record 를 하나 처리할 때마다 task_done() 을 부른다.
# 그래서 "unfinished_tasks == 0" 이 곧 "넣은 걸 전부 썼다" 는 뜻이다.
with log_queue.all_tasks_done:
    log_queue.all_tasks_done.wait_for(lambda: log_queue.unfinished_tasks == 0, timeout)
```

`Queue.join()` 이 기다리는 조건과 **같은 조건**이되, `join()` 에는 timeout 이 없어 직접
기다립니다. timeout 없이 썼다면 listener 가 죽어 있을 때 종료가 영원히 매달렸을 것입니다 —
**F-037** 이 정확히 그 함정이었습니다.

---

## 6. 정리 — 어떤 장치가 어떤 구멍을 막나

| 장치 | 막는 구멍 | 결정 |
|---|---|---|
| 큐 + listener 스레드 | 로깅이 event loop 를 막는 것 | NFR-009 |
| 중첩 `async with` | 취소 시 뒤 단계 정리가 건너뛰어지는 것 | ADR-017 / F-028 |
| listener 를 lifespan 이 **안** 멈춤 | lifespan 이후 로그·traceback 유실 | ADR-018 / F-029 |
| `atexit` 훅 | 정상 종료·`SIGINT` 에서 listener 정지 | ADR-018 |
| `SIGTERM`/`SIGBREAK` 핸들러 | `docker stop` 에서 `atexit` 이 안 도는 것 | ADR-022 / F-038 |
| lifespan 끝의 큐 flush | `uvicorn main:app` 경로의 꼬리 유실 | ADR-023 / F-039 |
| `enqueue_sentinel` timeout | 큐 포화 시 종료 실패 | ADR-021 / F-030 |
| `stop()` join 예산 | listener 가 안 멈출 때 프로세스가 안 죽는 것 | F-037 |

---

## 7. 손대기 전에 읽을 것

이 영역은 **단위 테스트로는 안 보이는 결함**이 사는 곳입니다. 문제가 lifespan 바깥
(프로세스 종료, 신호 처리, uvicorn 내부)에 있기 때문입니다. 실제로 이 구조를 고치기 전
391개 테스트가 전부 초록이었지만 결함 12건을 하나도 잡지 못했습니다.

그래서 **실제 서버 프로세스를 띄우는 통합 테스트**가 있습니다.

```
tests/integration/test_uvicorn_lifecycle.py
  ├─ 정상 종료 순서            (자원 해제 완료 → uvicorn shutdown → listener 정지)
  ├─ startup 실패 시 원인 출력  (F-029 가 고쳐졌다는 유일한 증거)
  └─ uvicorn CLI 경로의 꼬리    (F-039)

tests/utils/test_logs.py
  └─ 신호 종료 경로에서의 flush (F-038)
```

`test_uvicorn_lifecycle.py` 는 `DEBUG=false` 로 서버를 띄우므로 MySQL 은 필요 없지만, startup
필수 조건인 **Redis(`REDIS_HOST`/`REDIS_PORT`)에 닿지 못하면 모듈 전체가 skip** 됩니다.
skip 은 통과가 아니므로, 이 영역을 고쳤다면 Redis 를 띄운 뒤 결과 줄에 skipped 가 없는지
확인하세요.

```bash
docker run --rm -d --name fastapi-redis -p 6379:6379 redis:7-alpine
uv run python -m pytest tests/integration/test_uvicorn_lifecycle.py tests/utils/test_logs.py -rs
```

이 파일들을 지우거나 약화시키지 마세요. 여기 적힌 결함들은 **전부 한 번씩 실제로
일어났던 것**이고, 이 테스트들이 재발을 막는 유일한 장치입니다.
