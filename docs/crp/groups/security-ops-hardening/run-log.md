# Run Log — security-ops-hardening (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안
> 바뀌었으면 동일 요청은 "할 일 없음".

작업 기준선 base SHA: `49d9ee5` (main, 그룹 개설 직전). 브랜치 `feat/security-ops`. 코드 커밋 `6292e8b`.

## 라운드 기록

### Round 1 — 2026-10-19 · 원 명세 (바인드 값 · 접속 로그 보존 · 로그인 CSRF · 날짜 필터)
- **트리거:** REQ-001, REQ-002(사용자 결정)
- **현황(변경 전):**
  - 바인드 값 — `app/` 의 `create_async_engine`/`create_engine` 은 `app/core/db/session.py` 세 곳(writer·replica 팩토리·background)뿐이고
    셋 다 `hide_parameters=True`. 빠진 지점 없음(F-001 은 회귀 가드만).
  - 보존 — 설정·삭제 코드·스케줄 모두 없음. `beat_schedule={}`.
  - CSRF — 로그인 템플릿에 토큰 없음. sqladmin 0.32 `Admin.login` 은 GET 에서 컨텍스트 없이 템플릿을 그린다(소스 확인) → 템플릿 전역 함수로 결정.
  - 날짜 필터 — sqladmin `OperationColumnFilter._is_date_type` 이 `isinstance(type, (Date, DateTime))` 라 `UTCDateTime`(TypeDecorator)은
    문자열 그대로 바인딩된다. 연산 필터 프로토콜(`has_operator`·`get_operation_options_for_model`·`get_filtered_query(query, op, value, model)`)과
    `{% include filter.template %}` 를 소스로 확인.
- **결정:** ADR-001~006
- **신규 finding:** MED 1(F-002) · LOW 3(F-001·F-003·F-004) — 전부 Fixed

#### fail-on-revert (변이 → 실패한 테스트)

변이는 대상 파일을 작업 폴더 밖에 복사해 두고 적용 → 해당 테스트 실행 → 복사본으로 복원했다(`git checkout` 미사용). 21건 모두 실패,
복원 후 `git diff`·`git status` 해시가 변이 전과 같았다.

| 변이 | 실패 |
|---|---|
| writer 엔진의 `hide_parameters=True` 제거 | `test_db_hide_parameters.py` 4건 전부(예외 문자열·엔진 계약·생성 지점 수·로그 파이프라인) |
| background 엔진의 `hide_parameters=True` 제거 | `test_every_app_engine_hides_parameters` |
| 삭제 조건 `<` → `<=` | `test_only_rows_older_than_retention_are_deleted` |
| 배치 반복 제거(한 번만 지움) | `test_deletes_in_batches_and_commits_each_batch` |
| 커밋을 루프 밖 한 번으로 | `test_deletes_in_batches_and_commits_each_batch` |
| 보존 0 조기 종료 제거 | `test_zero_retention_deletes_nothing_without_querying` |
| 설정 `ge=0` 제거 | `test_negative_retention_setting_is_a_validation_error` |
| 기본값 365 → 0 | `test_setting_default_is_one_year_and_env_overrides` |
| beat 등록 제거 | `test_purge_task_is_registered_and_scheduled_daily_at_0330_local` |
| 태스크가 provider 대신 서비스를 직접 생성 | `test_purge_task_builds_service_through_home_provider` |
| `login` 의 CSRF 대조 제거 | `test_admin_login.py` 7건(누락·빈 값·틀림·세션 없음·다른 세션·회전·상수 시간) |
| CSRF 대조를 빼고 레이트 리밋부터 | `test_post_without_matching_csrf_token_is_403_before_rate_limit_and_credentials` 3건 |
| `hmac.compare_digest` → `==` | `test_csrf_comparison_is_constant_time` |
| 템플릿 hidden 필드 제거 | `test_login_page_renders_hidden_csrf_field_bound_to_session` |
| 그릴 때마다 새 토큰 | `test_failed_login_keeps_token_so_the_user_can_retry`·`test_login_page_renders_hidden_csrf_field_bound_to_session` |
| user 뷰를 sqladmin `OperationColumnFilter(created_at)` 로 되돌림 | `test_admin_views_render.py` 3건(필터 적용 500·뷰 적용 검사·목록 축소) |
| reports 뷰의 날짜 필터 제거 | `test_every_view_with_created_at_has_the_date_filter` |
| `OverflowError` 처리 제거 | `test_bad_input_is_ignored_with_warning[9999-12-31]` + 뷰 7개의 `overflow` 500 — 8건 |
| 로컬 자정 대신 UTC 자정 | `test_admin_date_filter.py` 4건(UTC 변환·연산 3종) |
| `on` 의 끝 경계를 포함(`<=`) | `test_operations_use_local_midnight_boundaries[on]` |
| `before` 를 포함(`<=`) | `test_operations_use_local_midnight_boundaries[before]` |

#### 검사

- `ruff check .` 통과 · `ruff format --check .` 322 files · mypy(격리 실행, 규칙 파일 방법) 203 source files 이상 없음.
- `pytest -m "not mysql"`: 작업 트리 **1146 passed · 0 skipped · 19 deselected** — Redis 가 필요한 uvicorn 수명주기 3건은 저장소 밖
  `fakeredis` TCP 서버(127.0.0.1:6391, `REDIS_PORT=6391`)로 함께 돌렸고 끝나고 종료.
- `.env` 없는 저장소 밖 클론(`6292e8b`, `uv sync --frozen`): **1146 passed · 0 skipped · 19 deselected**(같은 fakeredis).
- `pytest -m mysql --collect-only`: 19 수집(새 `test_retention_purge_on_mysql` 포함 — CI 가 돌린다).
- `review_gate --fast`: 전건 통과(pip-audit 포함 — 네트워크 가능했음).
- alembic: 마이그레이션 변경 없음(스키마 변경 없음 — `created_at` 인덱스는 이미 있다).
- **실기동 스모크:** 저장소 밖 런처가 클론의 앱 엔진을 SQLite 파일 DB 로 바꿔 끼우고(작업 디렉터리 저장소 밖, `.env` 없음, 설정은 환경
  변수로만, 비밀 값은 매번 생성·출력 안 함) 슈퍼유저 1명과 접속 로그 2행(오늘·10일 전)을 넣은 뒤 uvicorn 을 127.0.0.1:18766 에 띄웠다.
  Redis 는 fakeredis TCP(6391). curl 쿠키 jar 결과: `GET /admin/login` hidden 토큰 43자 · 토큰 없는 POST 403 · 틀린 토큰 403 ·
  맞는 토큰+틀린 비밀번호 400 · 맞는 토큰+비밀번호 302 · `GET /admin/` 200 · 7개 뷰 `?created_at=<오늘>&created_at_op=on` 200 ·
  잘못된 날짜(`2026-99-99`) 200 · 접속 로그 목록 `on 오늘` 은 `/today` 만, `before 오늘` 은 `/old` 만 · 목록에 `type="date"`·빠른 선택
  (오늘·최근 7일·최근 30일). 로그에 `날짜 필터 입력 무시` WARNING 14건(잘못된 날짜 요청 14회 — 7개 뷰 확인을 두 번 돌렸다)·
  `CSRF 토큰 불일치` 2건, traceback 0. 종료 후 포트 해제 확인.

- **수렴 판정:** `CONVERGED`
