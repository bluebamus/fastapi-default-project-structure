# Ledger — logging-overhaul (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope**(→ residual-risk) / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/테스트) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | INV-6 | Fix | Fixed | `6400d8e` · `test_redact_masks_known_secret_shapes[mysql…]` | DSN 의 비밀번호만 가리고 사용자명(`u:***@h`)은 원문으로 남았다 |
| F-002 | MED | INV-6 | Fix | Fixed | `6400d8e` · `test_configured_secret_values_*`·`test_short_account_name_is_masked_only_in_account_shapes`·`test_configured_secret_values_never_reach_any_output` | 설정 비밀번호·키를 `password=` 같은 키 없이 값만 로그에 넣으면 원문으로 나갔다 |
| F-003 | LOW | INV-1 | Fix | Fixed | `889ea93` · `test_every_path_uses_the_project_format` | uvicorn CLI·Celery 는 형식을 지정했을 때만 프로젝트 형식(config-cleanup R-005). 사용자 결정으로 항상 |
| F-004 | LOW | INV-4 | Fix | Fixed | `a9a8958` · `test_app_level_filter_applies_per_header_minimum`·`test_app_levels_filter_real_output` | 헤더(앱·서드파티)별 레벨을 줄 수 없었다(ADR-019 의 수용 위험) |
| F-005 | LOW | INV-5 | Fix | Fixed | `f43bf7f`·`1596f3c` · `tests/utils/test_log_rotation.py`·`tests/utils/test_log_files.py` | 파일 로그·회전·보관이 없었다(config-cleanup R-004) |
| F-006 | LOW | INV-2 | Fix | Fixed | `a9a8958` · `test_format_missing_required_fields_is_a_settings_error` | 사용자 포맷이 모듈·클래스·함수를 빼도 기동했다 |
| F-007 | LOW | INV-1 | Fix | Fixed | `1596f3c` · `test_configured_secret_values_never_reach_any_output`(uvicorn 줄이 app.log 에 있어야 한다) | 작업 중 발견: `configure_logging(force=True)` 로 재구성하면 uvicorn 로거에 **멈춘 옛 queue 핸들러**가 남아 그 줄이 사라졌다. 채택 함수가 현재 queue 가 아닌 핸들러를 모두 남의 것으로 본다 |
| F-008 | LOW | INV-5 | Fix | Fixed | 이 라운드 · `test_console_disabled_with_files_on_does_not_warn` | 콘솔을 꺼도 파일이 켜져 있으면 로그는 남는데 "앱 로그가 기록되지 않습니다" 경고를 냈다 |

<!--
규칙: 계약 위반만 Fix. Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Fixed. Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
