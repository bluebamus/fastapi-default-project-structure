# Ledger — admin-login (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope**(→ residual-risk) / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/테스트) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | HIGH | INV-1 — 관리 화면은 슈퍼유저 로그인 없이 열리지 않는다 | Fix | Fixed | Round 1 · `AdminAuthBackend` + `tests/test_admin_login.py`(`test_active_superuser_logs_in_and_reaches_index` · `test_failed_login_is_400_with_one_generic_message` · `test_demoted_superuser_is_rejected_on_next_request` · `test_create_superuser_then_admin_login_flow` 외) · `tests/integration/test_mysql_admin_login.py` | 출처: `service-hardening` R-001 · `orm-raw-repository` R-004. `/admin` 이 자격증명 없이 모든 모델을 조회·수정·삭제·CSV 내보내기 했다 |
| F-002 | LOW | ADR-007 — 태스크 모듈 import 오류는 CI 에서 드러난다 | Fix | Fixed | Round 1 · `test_every_include_module_imports_and_registers_its_tasks` | 탐색이 `find_spec` 만 해 `tasks.py` 오류가 워커 기동 때에야 보였다 |
| F-003 | MED | INV-4·INV-5 — 끈 관리 화면은 흔적이 없고, 뜻이 뒤집힌 예전 설정은 무시되지 않는다 | Fix | Fixed | Round 2 · `tests/test_admin_disabled.py`(4건) · `test_legacy_admin_env_var_stops_startup` · `test_legacy_admin_in_env_file_stops_startup` · `test_import_fails_when_legacy_admin_is_set` | 이전에는 `ADMIN=false` 가 끄는 유일한 방법이었고 OpenAPI 설명에 관리 화면 경로가 실렸다 |
| F-004 | LOW | REQ-001-A — 배포 전 할 일이 운영자가 보는 모든 곳에 일관된다 | Fix | Fixed | Round 1·2 · README 체크리스트 A~D, `.env.example`, config 주석·description, 리비전·`ClientIPResolver`·`create_superuser`·조립 지점 docstring, 가이드 4종 + 안내서 | `TRUSTED_PROXY_HOPS` 의 단점(0 이면 한 사람 취급)·리비전 오프셋 가정이 README 일부에만 있었다 |
| F-005 | MED | INV-1 의 전제 — 로그인한 슈퍼유저가 모든 관리 화면을 쓸 수 있다 | Fix | Fixed | Round 3 · 기능 `admin.py` 6개의 `column_filters` 를 `sqladmin.filters`(`BooleanFilter`·`OperationColumnFilter`)로 · `tests/test_admin_views_render.py`(뷰 7개 목록 · 필터 15건 · 상세 1건 · 정의 검사) | 감독자 확인 지시(다른 작업에서 발견된 같은 결함). sqladmin 0.32 는 필터 객체를 받는데 컬럼을 그대로 넘겨 목록 화면이 `AttributeError: ... 'parameter_name'` 으로 500 이었다. 생성 시각 필터는 연산 필터가 `UTCDateTime` 을 날짜 형으로 보지 못해(문자열 바인딩 → 500) 뺐다 — 변이로 확인 |

<!--
규칙: 계약 위반만 Fix. Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Fixed. Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
