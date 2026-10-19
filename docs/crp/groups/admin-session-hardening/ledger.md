# Ledger — admin-session-hardening (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope**(→ residual-risk) / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/테스트) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | INV-1·INV-4 — 관리 세션 서버 폐기·수명 | Fix | Fixed | Round 1 · `ba0e098` · `tests/test_admin_session.py` | 출처: admin-login R-001. 서명 쿠키라 로그아웃 전에 복사한 쿠키가 8시간 유효했고 미사용 만료가 없었다 |
| F-002 | MED | INV-2 — 권한 회수 뒤 관리 세션 | Fix | Fixed | Round 1 · `ba0e098` · `tests/test_admin_session.py`(폐기 7건) | 매 요청 DB 확인만 있어, 재활성화·재승격하면 옛 쿠키가 다시 통했다. 관리 화면의 사용자 수정·삭제는 `UserService` 를 거치지 않아 refresh 폐기도 없던 경로다(관리 세션 폐기만 더했다 — R-004) |
| F-003 | MED | INV-3 — 로그인 이후 CSRF | Fix | Fixed | Round 1 · `ba0e098` · `tests/test_admin_csrf.py`(34건) · `tests/test_admin_login.py`(갱신) | 출처: security-ops-hardening R-001. 생성·수정·삭제·로그아웃에 토큰이 없고 로그아웃이 GET 이었다 |
| F-005 | MED | INV-2 — 관리 화면 경로의 폐기 조건·실패 처리 | Fix | Fixed | Round 1 · `25901ae` · `tests/test_admin_session.py`(관리 화면 7건) | 출처: 감독자 추가 범위 REQ-003. 1차 구현(`after_*` 훅)은 변경 전후를 비교하지 않아 비활성·일반 사용자의 일반 수정에도 폐기했고, 비밀번호 변경을 보지 않았고, 커밋 뒤라 Redis 실패 시 "저장됨 + 세션 생존" 이 남았다 |
| F-004 | LOW | INV-5 — 기간 필터 | Fix | Fixed | Round 1 · `2768083` · `tests/core/test_admin_date_filter.py`(+13건) · `tests/test_admin_views_render.py`(+9건) | 출처: security-ops-hardening R-004 |

<!--
규칙: 계약 위반만 Fix. Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Fixed. Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
