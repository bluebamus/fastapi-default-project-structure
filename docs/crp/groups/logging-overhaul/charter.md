# Charter — logging-overhaul  (Charter v0.1 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 라운드 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 1 | `config.py` | 설정 | `LogSettings` 새 키(`LOG_FILE_*`·`LOG_DIR`·`LOG_MAX_SIZE_MB`·`LOG_RETENTION_DAYS`·`LOG_APP_LEVELS`), 필수 필드 검사, `parse_app_levels`, `LOG_SECRET_SETTINGS`·`log_secret_values` |
| 1 | `app/utils/logs/filters.py`·`formatters.py`·`config.py`·`setup.py`·`handlers.py`(신규)·`__init__.py` | 코드 | 헤더 표·`AppLevelFilter`·DSN 사용자명·비밀값 원문·`adopt_foreign_handlers`·`attach_log_files`·회전 핸들러, `StaticAppFilter` 삭제 |
| 1 | `app/celery/lifecycle.py`, `main.py` | 진입점 | 프로세스 종류 판단(`attach_log_files`), Celery 핸들러 채택 |
| 1 | `tests/utils/test_logs.py`·`test_log_settings_wiring.py`·`test_log_redaction.py`·`test_log_rotation.py`(신규)·`test_log_files.py`(신규), `tests/core/test_settings_usage.py` | 테스트 | |
| 1 | `.env.example`, `README.md`, `docs/guides/ARCHITECTURE.md`·`DEVELOPMENT.md`·`server-lifecycle-guide.html`, `scripts/review_gate.py` | 문서·스크립트 | 로깅 절·업그레이드 노트, 요구 ID 출처 |
| 1 | `docs/crp/groups/config-cleanup/residual-risk.md`·`log-redaction-fixes/residual-risk.md` | 이전 그룹 | 해소 상태 덧붙임(append-only) |

## 2. 계약 (Contract)

### 2-1. 지원 구성

- uvicorn 단일 워커(`python main.py`·`uvicorn main:app`) 또는 여러 워커 + 파일 로그 끔, Celery worker(`-P solo`·prefork). 파일 로그는
  한 `LOG_DIR` 을 한 프로세스(계열)만 쓸 때 보장한다.

### 2-2. 위협 모델

- 방어한다: 설정된 DB 계정·비밀번호·Redis 비밀번호·JWT/세션 키와 DSN 계정이 콘솔·파일·traceback 에 원문으로 남는 것.
- 방어하지 않는다: 설정에 없는 비밀(요청으로 받은 토큰 값 등)의 형태 밖 노출(log-redaction R-003 의 남은 부분),
  로그 파일 자체의 접근 권한(운영 몫).

### 2-3. 불변식

- **INV-1**: 앱·`python main.py`·`uvicorn main:app`·Celery worker(메인·태스크)의 콘솔·파일 줄은 같은 `TzFormatter`·포맷이다.
- **INV-2**: 모든 줄에 시각·레벨·헤더·모듈·클래스·함수·메시지가 있다 — 포맷이 빠뜨리면 기동하지 않는다.
- **INV-3**: 헤더는 한 함수가 정하고, 외부 코드는 로거 이름으로 `celery`·`uvicorn`·`sqlalchemy`·`alembic`·`ext`.
- **INV-4**: `LOG_APP_LEVELS` 의 헤더별 최소 레벨보다 낮은 줄은 어느 출력처에도 나가지 않는다. 지정 없는 헤더는 `LOG_LEVEL`.
- **INV-5**: 파일은 프로세스별(웹 `app.log`·`error.log`, Celery `celery.log`·`celery-error.log`)이고, 회전은 자정(로그 시각 시간대)·크기,
  보관은 `LOG_RETENTION_DAYS`(정확히 N일 전은 남김, 0 = 삭제 안 함). 회전은 기존 파일을 덮지 않는다.
- **INV-6**: `LOG_SECRET_SETTINGS` 의 값(4글자 이상)과 DSN 계정은 어떤 출력에도 원문으로 남지 않는다. 4글자 미만 값은 계정 형태에서만 가린다.
- **INV-7**: 파일 쓰기·회전은 요청 event loop 밖(listener 스레드)에서 일어난다.

## 3. 인수 기준 — 전부 그린

- [x] **L1 같은 형식** — `test_every_path_uses_the_project_format`·`test_custom_format_applies_to_uvicorn_cli_handlers`·`test_custom_formats_apply_to_celery_console_and_logfile`·`test_uvicorn_cli_access_line_is_masked_and_not_lost`
- [x] **L2 헤더** — `test_external_code_is_labeled_by_logger_name`·`test_our_code_keeps_path_label_whatever_the_logger_name`·`test_formatter_labels_records_that_skipped_the_context_filter`
- [x] **L3 필수 필드** — `test_format_missing_required_fields_is_a_settings_error`·`test_default_formats_have_every_required_field`
- [x] **L4 레벨** — `test_app_levels_parse_to_a_mapping`·`test_bad_app_levels_are_a_settings_error`·`test_app_level_filter_applies_per_header_minimum`·`test_logger_level_is_lowered_to_the_lowest_app_level`·`test_unknown_app_level_header_warns_but_starts`·`test_app_levels_filter_real_output`
- [x] **L5 파일** — `test_web_process_writes_app_log_and_error_log`·`test_celery_worker_writes_its_own_files`·`test_web_entry_point_attaches_the_web_files`·`test_file_level_applies_to_the_process_file_only`·`test_files_are_off_by_default`·`test_removed_keys_are_ignored`
- [x] **L6 회전·보관** — `tests/utils/test_log_rotation.py` 7건(자정·시간대·크기·덮지 않음·보관 경계·0)
- [x] **L7 비밀값** — `test_redact_masks_known_secret_shapes`(DSN)·`test_configured_secret_values_are_masked_anywhere`·`test_short_account_name_is_masked_only_in_account_shapes`·`test_secret_value_inside_exception_chain_is_masked`·`test_secret_values_come_from_settings`·`test_every_secret_like_setting_is_in_the_log_secret_list`·`test_configured_secret_values_never_reach_any_output`
- [x] **문서** — README·ARCHITECTURE·DEVELOPMENT·server-lifecycle·`.env.example`, HTML 은 `html.parser` 로 파싱 확인
- [x] **공통 게이트·fail-on-revert·실기동 스모크** — run-log

## 4. 변경 이력

- v0.1 (2026-10-19): 최초 작성(명세 L1~L9).
