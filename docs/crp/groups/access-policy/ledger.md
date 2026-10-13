# Ledger — access-policy (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope**(→ residual-risk) / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/테스트) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | INV-1 — 모든 뷰가 접근 수준을 선언 | Fix | Fixed | Round 1 · `AccessPolicyGuard` + `main.py` `verify(app)` · `tests/core/test_access_policy.py`(16건) · `test_main_refuses_to_start_when_a_view_declares_no_access_level` | 출처: log-redaction R-004(새 라우터의 인증 누락을 막는 장치 없음 — 기본값 공개). 변경 전에는 선언 없는 뷰가 그대로 공개로 떴다 |
| F-002 | LOW | INV-3 — 기대 표 하나 | Fix | Fixed | Round 1 · `EXPECTED_ACCESS` · `test_route_access_levels_match_the_policy_table` · `test_superuser_routes_are_403_for_normal_users` · `test_protected_routes_are_401_without_token` · `test_owned_cases_cover_every_login_created_collection` | 권한 테스트가 손으로 적은 `OWNED`·`ADMIN_ROUTES` 와 docstring 표 — 세 벌이었다. 새 보호 라우트는 어느 목록에도 저절로 들어가지 않았다 |

<!--
규칙: 계약 위반만 Fix. Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Fixed. Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
