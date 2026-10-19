# Ledger — config-cleanup (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope**(→ residual-risk) / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/테스트) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | LOW | INV-1 — 읽히지 않는 설정 | Fix | Fixed | Round 1 · `af0ec55` · `test_every_settings_field_is_read_somewhere` · `test_removed_keys_are_ignored` | `SMTPSettings` 8필드 — 메일 발송 코드가 없다. `SMTP_PASSWORD` 는 배포 검사만 읽었다 |
| F-002 | LOW | INV-1 | Fix | Fixed | Round 1 · 같은 커밋 · 같은 테스트 | `UploadSettings` 7필드 — 업로드 핸들러가 없다 |
| F-003 | LOW | INV-1·INV-3 | Fix | Fixed | Round 1 · 같은 커밋 · 같은 테스트 | `SESSION_EXPIRE_SECONDS`(24시간) — 세션 만료를 정하는 것처럼 보였지만 실제 만료는 `ADMIN_SESSION_*`·토큰 만료가 정한다 |
| F-004 | LOW | INV-1 — 재발 방지 | Fix | Fixed | Round 1 · `tests/core/test_settings_usage.py` | 정의만 있는 필드를 막는 검사가 없었다(`test_settings_contract.py` 는 `.env.example` ↔ config 만 본다) |
| F-005 | LOW | INV-1 | Fix | Fixed | Round 2 · `8dde820` · `test_removed_keys_are_ignored` · `test_every_settings_field_is_read_somewhere` | `API_VERSION` — 읽는 코드가 없고 바꿔도 경로가 바뀌지 않았다(R-001 일부) |
| F-006 | LOW | INV-1·INV-5 | Fix | Fixed | Round 2 · `8dde820` · `test_console_disabled_*` | `LOG_CONSOLE_ENABLED` — false 로 줘도 콘솔 출력이 꺼지지 않았다(R-001 일부) |
| F-008 | MED | INV-7·INV-6 — 비밀값 노출 | Fix | Fixed | Round 3 · `f52ef4f` · `test_filter_masks_inside_one_argument_and_keeps_args_shape` · `test_uvicorn_cli_access_line_is_masked_and_not_lost` | `uvicorn main:app` 의 접속 줄은 마스킹 필터가 없어 `?token=`·`?password=` 를 원문으로 냈다. 필터를 붙이면 `args=None` 때문에 `AccessFormatter` 가 줄을 잃는 형제 결함이 있어 제외돼 있던 것 — 필터가 `args` 모양을 지키게 하고 붙였다 |
| F-007 | LOW | INV-1·INV-4 | Fix | Fixed | Round 2 · `8dde820` · `test_custom_format_*` · `test_default_*` · `test_invalid_console_format_is_a_settings_error` | `LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT` — 읽히지 않았고, `LOG_CONSOLE_FORMAT` 기본값(`[{asctime}] {levelname:8} [{name}:…]`)이 실제 포맷과 달랐다(R-001 일부) |

<!--
규칙: 계약 위반만 Fix. Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Fixed. Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
