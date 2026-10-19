# Run Log — config-cleanup (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안
> 바뀌었으면 동일 요청은 "할 일 없음".

작업 기준선 base SHA: `350fc23` (main, 그룹 개설 직전). 브랜치 `chore/config-cleanup`. 코드 커밋 `af0ec55`.

## 라운드 기록

### Round 1 — 2026-10-19 · 원 명세 (SMTP · 업로드 · SESSION_EXPIRE_SECONDS 삭제 · 만료 정본 · 사용처 계약)
- **트리거:** REQ-001(사용자 결정), REQ-002~004
- **현황(변경 전):** 12개 Settings·79필드. AST 로 읽기를 모으면 읽히지 않는 필드는 `SMTP_*` 7개(`SMTP_PASSWORD` 는 배포 검사가 읽음,
  `SMTP_TLS`·`SMTP_SSL` 은 자기 validator 만 읽음), `UPLOAD_*` 7개, `SESSION_EXPIRE_SECONDS`, 그리고 범위 밖 `API_VERSION`·
  `LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT`. 모든 클래스가 이미 `extra="ignore"`.
  `python-multipart` 는 `Request.form()` 으로 쓰인다 — `app/features/auth/admin_backend.py`(로그인 폼),
  `app/core/security/admin_session.py`(`AdminCsrfMiddleware` 의 폼 토큰), sqladmin 생성·수정 폼.
- **결정:** ADR-001~004
- **신규 finding:** LOW 4(F-001~F-004) — 전부 Fixed. 변경 후 10개 Settings·63필드.

#### 참조 목록 (`git grep -i -E "smtp|SESSION_EXPIRE_SECONDS|upload"`, 변경 전 줄 번호)

| 파일 | 참조 | 처리 |
|---|---|---|
| `config.py` | `SessionSettings` docstring 929·필드 954, `SMTPSettings` 984~1059, `UploadSettings` 1062~1117, 팩토리 1184~1192, 전역 1210~1211, `validate_deployment_safety` 1307·1324·1335~1339·1367 | 삭제. docstring 은 "관리 세션 만료는 `ADMIN_SESSION_*` 가 정한다", 검사는 `REDIS_PASSWORD` 만 남김 |
| `.env.example` | 264(주석)·276(`SESSION_EXPIRE_SECONDS`), SMTP 절 320~351, 업로드 절 353~378 | 삭제, 264 주석 고침 |
| `tests/core/test_deployment_safety.py` | 51·73(`_check` 의 smtp), 166(비밀번호 3종), 179·444(subprocess 환경), 256~265(주석·`PASSWORD_KEYS`), 277(parametrize), 317~323(`test_placeholder_smtp_password_is_rejected`), 328~331, 341 | 삭제·2종으로. Redis 빈 값 테스트는 `test_unused_redis_password_passes` 로 이름만 바꿔 유지 |
| `README.md` | 134(§2 표), 234(검사 표), 251~252(만료 행), 420(체크리스트 4), 433 | SMTP 삭제, 만료는 새 `### 세션·토큰 만료` 표로, 업그레이드 노트 신설 |
| `docs/guides/ARCHITECTURE.md` | 422(12개), 430(SMTP validator), 440, 459(`SESSION_EXPIRE_SECONDS`), 460(`smtp_settings`·`upload_settings`), 914·1015(만료 기본값), 1231·1233~1238(부록) | 삭제·10개로, 만료는 README 표를 가리킴, §16 변경 이력 1행 |
| `docs/guides/DEVELOPMENT.md` | 99, 103 | 사용처 계약 테스트 언급, `SMTP_PASSWORD` 삭제 |
| `docs/guides/server-lifecycle-guide.html` | 84(소비 지점 표·validator·배포 검사 문단), 185(부록 표·"12개·76개") | 삭제, 10개·63개, Session 행 갱신(낡은 "소비 코드 없음" 정정), Middleware 필드 수 5→6 정정 |
| `docs/guides/admin-auth-guide.html` | (세 묶음 참조 없음) §13 표의 만료 기본값 | README 표를 가리키는 한 행으로 |
| `docs/crp/groups/orm-raw-repository/design-baseline.md` | 51·105·116·190 (`SMTP_PASSWORD`) | **고치지 않음** — 이력(append-only) |
| app·scripts·migrations·`.github`·`compose.test.yaml`·`pyproject.toml` | 없음 | — |

#### fail-on-revert (변이 → 실패한 테스트)

`config.py`·테스트 파일을 작업 폴더 밖에 복사해 두고 변이 → 테스트 → 복사본으로 복원(`cmp` 일치 확인, `git checkout` 미사용).

| 변이 | 실패 |
|---|---|
| 변경 전 `config.py`(main) 그대로 | `test_every_settings_field_is_read_somewhere`(SMTP 7·UPLOAD 7·`SESSION_EXPIRE_SECONDS`), `test_removed_keys_are_ignored[SessionSettings·SMTPSettings·UploadSettings]` — 4건 |
| `UPLOAD_DIR` 필드 하나만 되살림 | `test_every_settings_field_is_read_somewhere`(`['UPLOAD_DIR']`), `test_removed_keys_are_ignored[SessionSettings]` |
| validator 본문 제외를 끔(변경 전 `config.py` 에서) | `SMTP_TLS`·`SMTP_SSL` 이 "읽힘" 으로 바뀌어 보고에서 빠진다 — 제외 규칙이 실제로 일한다 |
| `UNUSED_ALLOWED` 에 쓰이는 필드(`SESSION_SECRET_KEY`) 추가 | `test_unused_allowlist_is_not_stale` |

#### 검사

- `ruff check .` 통과 · `ruff format --check .` 326 files · mypy(격리 실행, 규칙 파일 방법) 204 source files 이상 없음.
- `pytest -m "not mysql"`: 작업 트리 **1243 passed · 0 skipped · 19 deselected**(변경 전 1232 — SMTP 테스트 2건 삭제, 새 13건).
- `.env` 없는 저장소 밖 클론(`af0ec55`, `uv sync --frozen`): **1243 passed · 0 skipped · 19 deselected**.
- `pytest -m mysql --collect-only`: 19 수집.
- `review_gate --fast`: 전건 통과(pip-audit 포함 — 네트워크 가능했음).
- alembic: 마이그레이션 변경 없음.
- HTML 2편 `html.parser` 파싱 확인.

- **수렴 판정:** `CONVERGED`

### Round 2 — 2026-10-19 · config-cleanup-2 (API_VERSION 삭제 · 로그 설정 연결 · 예외 목록 삭제)
- **트리거:** REQ-005·REQ-006(사용자 결정 "API_VERSION 삭제, 로그 설정은 실제로 연결"). 기준선 main `cdfb44f`, 브랜치
  `chore/config-cleanup-2`, 코드 커밋 `8dde820`, 회귀 테스트 커밋 `eae4a99`.
- **현황(변경 전) — 로깅 흐름 조사:**
  - 앱: `configure_logging()` → `dictConfig(build_dictconfig())`. root 에는 `BoundedQueueHandler`(필터 `sql_noise`·`redact`·
    `context`) 하나, listener 가 `console`(stdout) 과 staging/production 의 `error_console`(stderr, ERROR) 에 쓴다. 포매터는
    `TzFormatter(fmt=LOG_FORMAT)` — `LOG_FORMAT` 은 `app/utils/logs/config.py` 의 **하드코딩 상수**, datefmt 는 넘기지 않아
    `TzFormatter.formatTime` 안의 하드코딩 `"%Y-%m-%d %H:%M:%S"`(+ development 밀리초), UTC 는 ENV 로 결정.
  - `python main.py`: `run_server()` 가 `uvicorn.run(log_config=setup_uvicorn_logging())` — uvicorn 3종 로거가 앱의 같은 queue
    핸들러를 쓴다(앱 포맷).
  - `uvicorn main:app` CLI: uvicorn 이 앱 import **전에** 자기 `LOGGING_CONFIG` 를 적용(`uvicorn`·`uvicorn.error` → stderr
    `DefaultFormatter "%(levelprefix)s %(message)s"`, `uvicorn.access` → stdout `AccessFormatter`). 앱은 `uvicorn`·`uvicorn.error`
    에 마스킹 필터만 붙였다.
  - Celery worker: 기본 `worker_hijack_root_logger` 로 root 핸들러를 지우고 자기 `StreamHandler(stderr)`(또는 `--logfile` 파일
    핸들러)와 Celery 포맷을 단다. `after_setup_logger`·`after_setup_task_logger` 수신자는 마스킹 필터만 붙였다.
  - `LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT` 은 어느 경로도 읽지 않았고, `LOG_CONSOLE_FORMAT` 기본값
    (`[{asctime}] {levelname:8} [{name}:{funcName}:{lineno}] {message}`)은 실제 포맷과 달랐다. `ApiSettings.API_VERSION` 도 읽는
    코드가 없었다(접두어 `/api`·`/v1` 은 `main.py`·각 기능 `router.py` 가 선언).
- **결정:** ADR-005~007
- **신규 finding:** LOW 3(F-005~F-007) — 전부 Fixed. 변경 후 9개 Settings·62필드, 읽히지 않는 필드 0, 예외 목록 없음. R-001 해소,
  R-004·R-005 수용.

#### fail-on-revert (변이 → 실패한 테스트)

변경한 파일을 작업 폴더 밖에 복사해 두고 변경 전 내용으로 바꿔 테스트 → 복사본으로 복원(`cmp` 일치 확인, `git checkout` 미사용).
새 테스트 파일은 `tests/utils/test_log_settings_wiring.py`(24건 — `8dde820` 21건 + `eae4a99` 3건).

| 변이 | 실패 |
|---|---|
| 테스트 먼저(구현 전) | 새 파일 16건 + `test_every_settings_field_is_read_somewhere` + `test_removed_keys_are_ignored[ApiSettings]` — 18 failed(기본 출력 회귀 가드 4건·정상 포맷 수용 1건은 통과) |
| 로깅 연결 코드 4개(`logs/config.py`·`setup.py`·`formatters.py`·`celery/lifecycle.py`)를 변경 전으로 | 11 failed — 사용자 포맷 5·콘솔 끄기 5·사용처 계약 1(`LOG_CONSOLE_*`·`LOG_DATE_FORMAT` 이 다시 안 읽힘) |
| `formatters.py` 만 | `test_default_app_output_is_unchanged[development]`·`test_custom_format_and_datefmt_apply_to_app_logger[development]`(밀리초 소실) |
| `celery/lifecycle.py` 만 | `test_custom_format_applies_to_celery_console_handler_not_file`·`test_console_disabled_keeps_celery_file_handler` |
| `config.py` 만 | 9 failed — 기본값 = 옛 포맷 4(기본 출력이 바뀜)·검증 5 |
| 콘솔 fmt 에 `{client_addr}` 를 덧붙임(검증 우회) | `test_main_py_access_log_renders_without_logging_error[default·custom]` — 줄마다 `Logging error` |

#### 검사

- `ruff check .` 통과 · `ruff format --check .` 327 files · mypy(격리 실행, 규칙 파일 방법) 204 source files 이상 없음.
- `pytest -m "not mysql"`(Redis 는 저장소 밖 fakeredis TCP, `REDIS_PORT`·`REDIS_TEST_PORT` 함께): 작업 트리
  **1265 passed · 0 skipped · 19 deselected** · `.env` 없는 저장소 밖 클론(`eae4a99`, `uv sync --frozen`): **1265 passed · 0 skipped · 19 deselected**
  (변경 전 1243 — 낡음 검사 1건 삭제, 새 24건, `ApiSettings` 파라미터 1건 삭제).
- `pytest -m mysql --collect-only`: 19 수집.
- 추가 확인(감독자 요청) — `python main.py` 경로의 uvicorn 접속 로그: 접속 레코드(msg·args 만)를 실제 `setup_uvicorn_logging()`
  dictConfig 로 흘려 봤다. 공유 `TzFormatter` 는 `{message}` 로 렌더해 기본·사용자 포맷 모두 오류 없이 요청 줄이 나오고(쿼리
  `password=` 마스킹, 시간대·`LOG_DATE_FORMAT` 반영), `{client_addr}` 류 접속 전용 필드를 쓰는 포맷은 설정 로드에서 거부된다 —
  **결함 없음**. 회귀 테스트 3건만 추가(`eae4a99`).
- `review_gate --fast`: 전건 통과(pip-audit 포함 — 네트워크 가능했음).
- alembic: 마이그레이션 변경 없음.
- HTML 안내서 2편(`server-lifecycle-guide.html`·`feature-development-guide.html`)과 로컬 review 문서 2편 `html.parser` 파싱 확인.

- **수렴 판정:** `CONVERGED`
