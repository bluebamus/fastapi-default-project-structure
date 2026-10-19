# Ledger — security-ops-hardening (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope**(→ residual-risk) / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/테스트) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | LOW | INV-1 — 엔진이 바인드 값을 싣지 않는다 | Fix | Fixed | Round 1 · `6292e8b` · `tests/core/test_db_hide_parameters.py`(4건) | 결함은 없었다 — 3곳 모두 이미 `hide_parameters=True`(service-hardening ADR-022). 기존 계약 테스트(`test_application_engines_hide_bound_parameters`)는 엔진 객체만 봤다 — 새 생성 지점·실제 예외 문자열·로그 출력은 고정돼 있지 않아 회귀 가드를 더했다 |
| F-002 | MED | INV-2 — 접속 로그 보존 | Fix | Fixed | Round 1 · `6292e8b` · `app/features/home/tests/test_access_log_retention.py`(10건) · `tests/integration/test_mysql_access_log_retention.py`(CI) | 출처: log-redaction R-001("보존 기간 정책도 없다"). IP·UA·`session_id`·Referer 원문이 무기한 쌓였다 |
| F-003 | LOW | INV-3 — 로그인 CSRF | Fix | Fixed | Round 1 · `6292e8b` · `tests/test_admin_login.py`(새 9건 + 기존 갱신) | 출처: admin-login R-002. 토큰이 없어 로그인 CSRF 와 위조 POST 로 피해자의 시도 한도(429)를 소진시키는 것이 가능했다 |
| F-004 | LOW | INV-4 — 날짜 필터 500 없음 | Fix | Fixed | Round 1 · `6292e8b` · `tests/core/test_admin_date_filter.py`(11건) · `tests/test_admin_views_render.py`(+37건) | 출처: admin-login ADR-009·F-005 — 생성 시각 필터를 500 때문에 뺐다. 관리 목록에서 날짜로 좁힐 방법이 없었다 |

<!--
규칙: 계약 위반만 Fix. Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Fixed. Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
