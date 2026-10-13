# Run Log — access-policy (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안
> 바뀌었으면 동일 요청은 "할 일 없음".

작업 기준선 base SHA: `3629493` (main, 그룹 개설 직전). 브랜치 `feat/access-policy`. 코드 커밋 `88130c7`.

## 라운드 기록

### Round 1 — 2026-10-13 · 원 명세 (뷰 단위 접근 수준 · 기동 시 기본 거부 · 테스트 정리)
- **트리거:** REQ-001
- **현황(변경 전):** 가드를 먼저 만들어 변경 전 앱(40 라우트)에 돌렸다 — 판정 없는 라우트 15건: blog·sns·reply·catalog 의
  GET 8, auth `register`·`login`·`refresh`·`logout` 4, `/health`·`/ready`·`/docs` 3. 나머지 25건은 인자 `CurrentPrincipal`·
  `require_superuser`(뷰·라우터 단위)·`get_current_user` 로 이미 수준이 판정됐다. 선언을 강제하는 장치가 없어 빠뜨린 뷰는
  그대로 공개로 떴다(F-001).
- **펼침 확인:** FastAPI 0.141 은 `app.routes` 에 `_IncludedRouter` 를 두고, `fastapi.routing.iter_route_contexts` 가
  `effective_route_contexts` 를 감싸 전체 경로·라우터 단위 의존성까지 합친 dependant 를 준다. `/admin` 은 `Mount`, FastAPI
  문서 경로는 Starlette `Route` 라 대상 밖. DEBUG 의 Scalar `/docs` 는 `APIRoute`(`include_in_schema=False`)라 대상 — `Public`.
- **OpenAPI 불변:** 변경 전후 `app.openapi()` 를 `sort_keys` JSON 으로 저장해 `cmp` — 동일(111,675 바이트). home·reports 는
  `responses=FORBIDDEN_RESPONSES` 를 라우터 단위로 남겨 응답 문서 병합 순서까지 같다.
- **401/403 선행 확인:** 인증 의존성이 본문·쿼리 검증보다 먼저 풀려, 본문 없이·경로 변수 임의 값으로도 401/403 이 난다
  (표에서 뽑은 실요청 38건 통과 — 슈퍼유저 13건 403, 보호 25건 401).
- **결정:** ADR-001~004
- **신규 finding:** MED 1(F-001) · LOW 1(F-002) — 전부 Fixed

#### fail-on-revert (변이 → 실패한 테스트)

| 변이 | 실패 |
|---|---|
| `main.py` 의 `AccessPolicyGuard().verify(app)` 제거 | `test_main_refuses_to_start_when_a_view_declares_no_access_level` |
| `levels()` 의 슈퍼유저 접기 제거 | `test_each_level_alone_on_its_methods_passes`·`test_principal_arguments_count_as_declarations`·`test_superuser_absorbs_login_it_uses_internally`·`test_router_level_and_include_level_dependencies_count`, 실제 앱도 `main` import 실패(슈퍼유저 라우트 13건이 이중 선언으로 잡힘) |
| `routes()` 가 중첩을 펼치지 않음(`RouteContext(r) for r in app.routes`) | `test_router_level_and_include_level_dependencies_count`·`test_nested_includes_are_expanded_with_their_full_path`·`test_route_access_levels_match_the_policy_table` |
| `include_in_schema=False` 제외 | `test_routes_hidden_from_the_schema_are_still_checked` |
| 쓰기+`Public` 검사 제거 | `test_public_on_a_write_method_points_to_public_write`[post·put·patch·delete] |
| 오류 메시지에 첫 위반만 | `test_verify_raises_with_every_violation_listed` |
| blog 목록의 `Public` 제거 | 수집 단계에서 `main` import 실패(`AccessPolicyError`) — 기본 거부 자체 |
| blog 목록 `Public` → `LoginRequired` | `test_route_access_levels_match_the_policy_table`·`test_reads_are_public[blog]` |
| catalog 생성 `SuperuserRequired` → `LoginRequired` | `test_route_access_levels_match_the_policy_table`·`test_superuser_routes_are_403_for_normal_users[POST /api/v1/catalog/products]` |

변이는 작업 폴더 밖 복사본으로 복원했다(`git checkout` 미사용).

#### 검사

- `ruff check .` 통과 · `ruff format --check .` 315 files · mypy(격리 실행, 규칙 파일 방법) 201 source files 이상 없음.
- `pytest -m "not mysql"`: 작업 트리 **1072 passed · 3 skipped · 18 deselected**(기준선 main 은 1043 선택 → 이번 1075 선택).
  skip 3건은 Redis 가 필요한 uvicorn 수명주기 — 저장소 밖 `fakeredis` TCP 서버(127.0.0.1:16399)로 따로 돌려 **3 passed**, 끝나고 종료.
- `.env` 없는 저장소 밖 클론(`88130c7`, `uv sync --frozen`): **1072 passed · 3 skipped · 18 deselected**(skip 은 같은 Redis 3건).
- `pytest -m mysql --collect-only`: 18 수집(로컬 MySQL 미실행 — CI 가 돌린다).
- `review_gate --fast`: 전건 통과(pip-audit 포함 — 네트워크 가능했음).
- alembic: 마이그레이션 변경 없음.

- **수렴 판정:** `CONVERGED`
