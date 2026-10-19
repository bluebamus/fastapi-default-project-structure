# Run Log — logging-overhaul (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안
> 바뀌었으면 동일 요청은 "할 일 없음".

작업 기준선 base SHA: `be9807b` (main, 그룹 개설 직전). 브랜치 `feat/logging-overhaul`.
코드 커밋 `6400d8e`(L7) · `74bc7f1`(L2) · `a9a8958`(L3·L4) · `889ea93`(L1) · `f43bf7f`(L6) · `1596f3c`(L5) · `0c5384e`(경고 조건·docstring), 문서 `efff866`.

## 라운드 기록

### Round 1 — 2026-10-19 · 원 명세 (L1~L9)
- **트리거:** REQ-001~007(사용자 요구·결정 2026-10-19)
- **현황(변경 전) — 로깅 흐름 조사:**
  - 앱: 첫 `get_logger()` → `configure_logging()` → `dictConfig(build_dictconfig())`. root 에는 `BoundedQueueHandler` 하나,
    필터 `sql_noise → redact → context` 가 적재 전 요청 스레드에서 돈다. listener(`TimeoutSentinelListener`)가 `console`(stdout)·
    `error_console`(staging/production stderr)에 쓴다. 파일 핸들러·rotation 은 NFR-009 로 제거된 상태(옛 `{date}_app.log` 는
    `f88dc5f` 이전 설정 `LOG_APP_FILENAME`·`LOG_ERROR_FILENAME`·`LOG_BACKUP_COUNT`·`LOG_FILE_ENABLED=true`·`LOG_MAX_SIZE_MB=10`).
  - `python main.py`: `run_server()` → `uvicorn.run(log_config=setup_uvicorn_logging())` — uvicorn 3종이 공유 queue + `StaticAppFilter("uvicorn")`.
  - `uvicorn main:app` CLI: uvicorn 이 `LOGGING_CONFIG` 를 먼저 적용하고 앱을 import. `configure_logging()` 이 uvicorn 로거에
    `RedactingFilter` 를 붙이고 `apply_console_settings()` 가 **포맷을 직접 지정했을 때만** `TzFormatter` 로 바꿨다(기본은 `INFO:     …`).
    헤더는 `TzFormatter` 의 기본값 `app`(uvicorn 이 아님).
  - Celery: worker 가 root·`celery.task` 핸들러를 갈아끼운 뒤 `after_setup_logger`·`after_setup_task_logger` 수신자가
    `apply_console_settings()`(같은 조건)와 핸들러별 `RedactingFilter`. `--logfile` 은 Celery 포맷 그대로.
  - `LogSettings`: `LOG_CONSOLE_ENABLED`·`LOG_SQL_ECHO_ENABLED`·`LOG_LEVEL`·`LOG_CONSOLE_LEVEL`·`LOG_CONSOLE_FORMAT`(렌더 검사)·`LOG_DATE_FORMAT`.
  - 마스킹: `_SECRET_PATTERNS` 의 DSN 패턴은 비밀번호만(`u:***@h`). 설정 값 원문 치환 없음.
  - 재사용: `TzFormatter`·`console_formatter_kwargs()`·`console_enabled()`·`RedactingFilter`/`redact()`·`ContextFilter`·`_app_from_path`·
    queue/listener 구조·`TimedRotatingFileHandler`(stdlib). 새로 만든 것은 필터 1(`AppLevelFilter`)·핸들러 1·함수 2(`adopt_foreign_handlers`·`attach_log_files`).
- **결정:** ADR-001~008
- **신규 finding:** MED 2(F-001·F-002) · LOW 6(F-003~F-008) — 전부 Fixed.

#### fail-on-revert

변경한 원본 9개(`app/celery/lifecycle.py`·`app/utils/logs/{__init__,config,filters,formatters,setup}.py`·`config.py`·`main.py`, 새 `handlers.py` 는 삭제)를
`be9807b` 로 되돌리고 새·바뀐 테스트를 돌린 뒤 복사본으로 복원했다.

| 대상 | 결과(변경 전 코드) |
|---|---|
| `tests/utils/test_log_rotation.py` | 수집 오류(`app.utils.logs.handlers` 없음) — 7건 전부 실패 |
| `tests/utils/test_log_files.py` | 6건 전부 실패 |
| `tests/utils/test_logs.py` | 새 15건 실패(헤더 표·포매터 대체 헤더·queue 필터 목록·`AppLevelFilter`·최솟값 레벨·모르는 헤더 경고) |
| `tests/utils/test_log_settings_wiring.py` | 새·바뀐 20건 실패(모든 경로 같은 형식·CLI/Celery 사용자 포맷·콘솔 끔·필수 필드·`LOG_APP_LEVELS`·파일 키·경고 조건) |
| `tests/utils/test_log_redaction.py` | 새·바뀐 15건 실패(DSN 사용자명·원문 치환·짧은 값·예외 체인·설정 목록·계약·CLI 접속 줄 형식) |
| 통과한 것 | `test_removed_keys_are_ignored` 의 새 옛 키 3개 — `extra="ignore"` 계약(코드 변경 없이 성립, config-cleanup ADR-002) |

`test_console_disabled_with_files_on_does_not_warn` 은 `setup._warn_if_no_output` 의 조건 한 줄만 되돌려 실패를 따로 확인했다.

#### 검사

- `ruff check .` 통과 · `ruff format --check .` 330 파일 · mypy(격리 실행) 205 파일 이상 없음.
- `pytest -m "not mysql"`(Redis 는 저장소 밖 fakeredis TCP, `REDIS_HOST`·`REDIS_PORT`): 작업 트리 **1314 passed · 0 skipped · 19 deselected** ·
  `.env` 없는 저장소 밖 클론(`efff866`, `uv sync --frozen`) **1314 passed · 0 skipped · 19 deselected**.
- `pytest -m mysql --collect-only`: 19 수집. `review_gate` 의 네트워크 없는 검사 9종 전건 통과(pytest·pip-audit 단계는 생략 — pytest 는 위,
  pip-audit 은 네트워크). alembic 변경 없음. `server-lifecycle-guide.html` 과 `docs/review` 두 문서 `html.parser` 파싱 확인.
- 주의: 이 라운드 초기의 전체 실행 2회는 `REDIS_PORT` 를 주지 않아 `tests/integration/test_uvicorn_lifecycle.py` 가 로컬 기본 포트(6379)의
  기존 Redis 에 닿았다. 이후 실행은 모두 fakeredis 로 돌렸다.

#### 실기동 스모크 (저장소 밖 tmp, `.env` 없음, 환경 변수만 — `ENV=development`·`DEBUG=false`·`LOG_FILE_ENABLED=true`, MySQL 은 닫힌 포트, Redis 는 fakeredis)

| 실행 | 요청·태스크 | 콘솔 | 파일 | 비밀값 원문 |
|---|---|---|---|---|
| `uvicorn main:app` | `/health` 200 · `/ready` 503 · `/nope?password=…&who=…` 404 | 프로젝트 형식 아닌 줄 0, `INFO:     ` 0 | `app.log` 76줄 · `error.log` 8줄 | 0 |
| `python main.py` | 같다 | 같다 | `app.log` 86줄 · `error.log` 8줄 | 0 |
| `celery worker --pool=solo -l INFO` | `home.aggregate_access_stats` 1건(DB 닫힘 → raised) | 같다 | `celery.log` · `celery-error.log` | 0 |

출력 예(같은 형식·헤더):

```text
[2026-10-19 18:22:46.369 KST] INFO  [app=app] [main:-:<module>:311] API 문서 비활성화 (운영 모드): 보안을 위해 /docs, /openapi.json 접근 차단
[2026-10-19 18:22:46.723 KST] INFO  [app=uvicorn] [httptools_impl:RequestResponseCycle:send:482] 127.0.0.1:65237 - "GET /health HTTP/1.1" 200
[2026-10-19 18:24:26.721 KST] ERROR [app=core] [repository_base:UserAccessLogRepository:_translated_errors:98] [COUNT] DB 오류 (model=UserAccessLog): OperationalError(code=2003)
[2026-10-19 18:24:24.690 KST] INFO  [app=celery] [strategy:-:task_message_handler:161] Task home.aggregate_access_stats[92b7c6c8-…] received
```

fakeredis 는 Lua(`EVALSHA`)가 없어 Celery worker 종료 때 `Unrecoverable error: ResponseError("unknown command 'evalsha'")` 가
`celery-error.log` 에 traceback 과 함께 남았다 — 스모크 환경의 한계이고 로깅 동작과 무관하다(형식·헤더는 같다).

#### 후속 확인 (감독자 지시) — DSN 모양과 접속 줄 포매터

- `config.RedisSettings.REDIS_URL` 은 `redis://:{quote(pw, safe="")}@host:port/db`(사용자명 빈 꼴, `@`·`:` 는 퍼센트 인코딩)다.
  DSN 비밀번호 패턴은 사용자명을 0자 이상으로 받아 이 꼴은 원래 가려졌다. 대신 **인코딩하지 않은 `@`** 가 든 비밀번호는 첫 `@`
  까지만 가려 나머지가 남았다(F-009) — 비밀번호를 마지막 `@` 까지 잡게 고쳤다. 빈 사용자명·사용자명만·`@`·`:` 든 비밀번호를
  `test_redact_masks_known_secret_shapes` 에 고정. fail-on-revert: 옛 패턴 → `@` 두 건 실패, 사용자명을 1자 이상으로 바꾼 변이 →
  빈 사용자명 세 건 실패.
- 접속 줄 포매터: `uvicorn.access` 레코드의 메시지가 이미 `client - "GET /p HTTP/1.1" 200` 이라 프로젝트 형식의 `{message}` 로
  충분하다 — `TzAccessFormatter` 는 두지 않는다(ADR-001). `python main.py` 경로가 원래 그렇게 출력했고 CLI 경로도 같은 queue 로 바뀌었다.

- **수렴 판정:** `CONVERGED`
