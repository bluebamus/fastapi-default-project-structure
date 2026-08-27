# lifespan 종료 조립 리팩터링 보고서

| 항목 | 값 |
|---|---|
| 작성일 | 2026-08-25 |
| 요구 | REQ-007 · 결정 ADR-016 · 결함 F-026 |
| 범위 | `app/core/resources.py` 한 파일 (+ 문서 정합) |
| 계약 변경 | **없음** — 종료 순서·자원별 timeout·실패 격리 불변 |
| API 영향 | 없음 — 공개 경로·응답 스키마·상태 코드 불변 (게이트 INV-11 그린) |
| DB 스키마 영향 | 없음 |

---

## 1. 무엇을 바꿨나

### Before

```python
try:
    async with AsyncExitStack() as cleanup:
        # 등록 역순으로 실행된다 → 원하는 종료 순서의 역순으로 등록한다.
        cleanup.push_async_callback(_stop_log_listener)       # 3번째로 실행
        cleanup.push_async_callback(_dispose_db_engines)      # 2번째로 실행
        cleanup.push_async_callback(_drain_background_tasks)  # 1번째로 실행

        resources.log_listener = start_log_listener()
        await _prepare_database(resources)

        logger.info("[startup] 자원 초기화 완료 (%.1fms)", elapsed)
        yield resources
        logger.info("[shutdown] 애플리케이션 자원 해제 시작")
finally:
    app.state.resources = None
    logger.info("[shutdown] 애플리케이션 자원 해제 완료")   # ← 출력되지 않음 (F-026)
```

### After

```python
try:
    # 이미 살아 있으면(모듈 import 시 시작됨) 그대로 쓴다 — 소유권만 여기로.
    resources.log_listener = start_log_listener()

    await _prepare_database(resources)

    logger.info("[startup] 자원 초기화 완료 (%.1fms)", elapsed)
    yield resources
finally:
    # 종료 순서는 이 블록의 **코드 순서 그대로**다. 각 단계를 _run_cleanup 이
    # 감싸 예외·timeout 을 삼키므로, 앞 단계가 실패해도 뒤 단계가 건너뛰어지지
    # 않는다 — 이 보장이 _run_cleanup 에 있으므로 ExitStack 이 필요 없다.
    logger.info("[shutdown] 애플리케이션 자원 해제 시작")

    await _drain_background_tasks()  # 1. DB 를 쓰는 주체를 먼저 멈춘다
    await _dispose_db_engines()      # 2. 커넥션 풀을 닫는다

    # 닫힌 자원을 다음 lifespan/테스트가 재사용하지 않도록 참조도 지운다.
    app.state.resources = None
    # listener 를 멈추기 **전에** 마지막 로그를 남긴다. 멈춘 뒤에 찍으면 큐를
    # 소비할 스레드가 없어 이 줄이 어디에도 출력되지 않는다.
    logger.info("[shutdown] 애플리케이션 자원 해제 완료")

    await _stop_log_listener()       # 3. 앞 단계의 로그까지 받은 뒤 마지막에 멈춘다
```

### 얻은 것 / 잃은 것

| | 내용 |
|---|---|
| 얻음 | 종료 순서가 **코드 순서와 일치** — `# 3번째로 실행` 류 주석 3줄 제거 |
| 얻음 | 한 파일 안에서 위→아래로 읽으면 종료 절차가 그대로 보인다 |
| 얻음 | F-026 수정 — 출력된 적 없던 종료 완료 로그가 살아났다 |
| 잃음 | **없음** — 부분 정리는 애초에 작동하지 않았고(§ 분석 문서 §4), 실패 격리는 `_run_cleanup()` 소관 |

---

## 2. F-026 — 한 번도 출력된 적 없는 로그

`"[shutdown] 애플리케이션 자원 해제 완료"` 는 `finally` 에서 찍혔는데, 그 시점엔
`AsyncExitStack` 이 **이미 logging listener 를 멈춘 뒤**였다. 큐를 소비할 스레드가 없으니
이 줄은 어디에도 나오지 않았다.

- **왜 안 드러났나**: 로그가 사라지는 것 자체는 아무 오류도 내지 않는다. 스스로 알아챌 방법이 없다.
  F-018 의 "존재하지 않는 환경변수 8개"(설정한 사람은 파일 로그가 생길 거라 믿었다)와 같은 계열이다.
- **위반 계약**: NFR-008 — 자원별 생성·close 성공과 실패를 기록한다
- **어떻게 찾았나**: 코드를 읽어서가 아니라, 리팩터 **전후로 실제 앱을 기동·종료해**
  이 줄의 부재와 출현을 대조했다
- **수정**: 마지막 로그를 `_stop_log_listener()` **앞**으로 이동
- **심각도**: LOW (관측성 손실이며 자원 누수는 아니다)

---

## 3. 변경 파일 전체

### 코드 (1)

| 파일 | 변경 |
|---|---|
| `app/core/resources.py` | `AsyncExitStack` → `try/finally`, import 제거, F-026 수정, 모듈 독스트링·`_run_cleanup` 독스트링 정정 |

### 그룹 거버넌스 문서 (4)

| 파일 | 변경 |
|---|---|
| `docs/crp/groups/orm-raw-repository/design-baseline.md` | v0.5 — REQ-007 등록 + **ADR-016** 확정 |
| `docs/crp/groups/orm-raw-repository/ledger.md` | F-026 기록 · 검수 라운드 R-11 · Open Fix 0 유지 |
| `docs/crp/groups/orm-raw-repository/checklist.md` | Round 11 추가 · 종결 상태 갱신 |
| `docs/crp/groups/orm-raw-repository/run-log.md` | Round 11 + 심각도 추세표(누계 25건) |

### 사용자 문서 (2)

| 파일 | 변경 |
|---|---|
| `docs/ARCHITECTURE.md` | §4.2 의 ExitStack 설명 정정 + 변경 이력 추가 |
| `docs/orm-raw-repository/2026-08-13/workflow-guide.md` | §11 예시 코드를 실제 구조로 교체 + ADR-016 이관 주석 |

### 고치지 않은 것 (의도적)

`requirements.md` 와 `development-plan.md` 는 **손대지 않았다.** ADR-010 이 세운 원리 —
요구 명세를 사후에 코드에 맞춰 고치면 "요구를 코드에 맞춘" 것이 되므로, 확장·이탈은
append-only 인 design-baseline 에 쌓는다 — 를 따랐다.

---

## 4. 왜 테스트를 고치지 않았나

`tests/core/test_resources.py` 13건을 **한 줄도 수정하지 않고** 통과시켰다. 이것이 이번
리팩터의 핵심 증거다.

구조를 바꾸면서 테스트를 같이 고쳤다면 "무엇이 보존됐는가"를 말할 수 없다. 테스트가
검사하는 것(종료 순서, startup 실패 cleanup, 재진입 누수, timeout 예산, 취소 태스크 회수)이
전부 그대로 그린이라는 사실이 곧 **계약 불변의 증명**이다.

검증 상세는 [`verification-report.md`](./verification-report.md) 에 있다.
