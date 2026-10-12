# Run Log — service-hardening (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.
> 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안 바뀌었으면 동일 요청은 "할 일 없음".

작업 기준선 base SHA: `eb70fbf` (그룹 개설 직전 커밋). 라운드 하나 = 단계 하나(ADR-001).

## 라운드 기록

### Round 1 — 2026-10-12 · 단계 A (base SHA: `eb70fbf`, 커밋 `66d4152`~`1639782`)
- **트리거:** 사용자 요청 REQ-001 (제안 1·2·3)
- **검수 범위:** CI 설치 단계, 게이트 파일 수집, DSN 조립·소비처 전수(`session.py`·`resources.py`·
  `app/celery/app.py`·`migrations/env.py`), 라우터 판정 두 경로(라우팅·읽기 세션), ORM 목록·시각 정렬 쿼리 전수
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 ☑ 5 ☑ — `pytest -m "not mysql"` **669 passed · 8 deselected · skipped 0**,
  ruff check·format 그린, mypy 188 파일 무결, `review_gate --fast` 전건 통과(ENV=test), `-m mysql` 8건 수집
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 3 · LOW 2 (F-001~F-005)
- **신규 Fix(계약 위반):** 5 건 → ledger F-001 ~ F-005, 전부 Fixed
- **fail-on-revert:** 대상 파일을 `eb70fbf` 내용으로 되돌려 새 테스트를 돌렸다.
  - A1 — `test_every_uv_sync_is_locked` 실패(`--frozen` 2줄), `test_untracked_files_are_not_listed` 실패
    (git 목록 대신 rglob 이면 추적 안 된 파일이 섞인다)
  - A2 — `tests/core/test_dsn.py` 5건 실패(Redis 는 `Port could not be cast to integer value as 'w'`),
    `test_percent_in_url_survives_alembic_config` 실패(`invalid interpolation syntax`). `%%` 치환만 뺀 경우에도 실패.
    `test_masked_rendering_hides_the_password` 는 옛 `mask_dsn` 도 통과한다(회귀 방지용)
  - A3 — 잠금 읽기 6건(라우팅 2 · 읽기 세션 라우터 on/off × 2) 실패, 동률 정렬 7건 실패.
    `test_offset_pages_do_not_overlap_and_cover_every_row` 는 SQLite 가 정렬 없이도 삽입 순서를 지켜 옛 코드도
    통과한다 — 결정성 자체는 동률 정렬 테스트가 지킨다
- **기존 테스트 영향:** `tests/core/test_db_router.py` 의 DSN 문자열 비교 9곳을 `make_url` 의미 비교로 바꿨다.
  삽입 순서에 기대던 테스트는 없었다(목록 순서를 단언하는 기능 테스트 전수 확인)
- **수렴 판정:** `CONVERGED` (Open Fix 0 — 단계 A 범위)
- **잔여 위험 변화:** R-001~R-009 최초 등록(그룹 개설)
- **실행 환경 주석:** 로컬 Windows 에서 `.venv` 의 mypy(mypyc 컴파일 DLL)가 애플리케이션 제어 정책에 막혀,
  같은 버전(1.20.2)의 순수 Python 빌드를 저장소 밖 경로에 두고 `PYTHONPATH` 로 앞세워 실행했다. 로컬에 Redis 가
  없어 uvicorn 수명주기 3건이 skip 되는 것을 막으려고 저장소 밖에서 fakeredis TCP 서버(127.0.0.1:6379)를 띄워
  돌렸다 — CI 는 `compose.test.yaml` 의 `redis-test` 를 쓴다. 저장소 파일은 바꾸지 않았다

### Round 2 — 2026-10-12 · 단계 B (base SHA: `85261dd`, 커밋 `4cd4b6b`~`b5dfade`)
- **트리거:** 사용자 요청 REQ-001 (제안 4·5)
- **검수 범위:** 접속 로그 미들웨어 전 경로(IP·예외·쿼리·쿠키·저장 직전 길이), Update 스키마 5종, DB 오류 변환의
  모든 호출처(ORM Base 8개 공개 메서드·Raw Base·기능 Repository 의 직접 `execute` 전수 — catalog 2·home 7·
  user 1), 엔진 생성 3곳, 리포트 기간 검증(조회·적재), `main.py` 예외 핸들러 4종
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 ☑ 5 ☑ — `pytest -m "not mysql"` **742 passed · 8 deselected · skipped 0**,
  ruff check·format 그린, mypy 191 파일 무결, `review_gate --fast` 전건 통과(ENV=test, INV-11 공개 API 불변 —
  OpenAPI 기준선 변경 없음), `-m mysql` 8건 수집
- **신규 finding(심각도별):** CRIT 0 · HIGH 1 · MED 5 · LOW 3 (F-006~F-013 + F-025 — F-025 는 검수 R-07 을 이 라운드에서 원장에 올렸다)
- **신규 Fix(계약 위반):** F-006 ~ F-013 + F-025, 전부 Fixed
- **결정:** ADR-021(ADR-006 의 홉 계수 해석, 기본값 0 의 동작 변경), ADR-022(변환 표 단일 클래스·기능 쿼리 경유·
  로그/엔진 비노출). 500 핸들러의 `str(exc)` 노출은 `DEBUG=true` 에서만이고 staging/production 은 DEBUG 를
  거부하므로 그대로 둔다 — `hide_parameters` 로 DEBUG 에서도 바인딩 값은 빠진다
- **fail-on-revert:** 대상 파일을 `85261dd` 내용으로 되돌려(백업은 저장소 밖) 새 테스트를 돌렸다.
  - B1 — `ClientIPResolver.resolve` 를 옛 규칙(XFF 맨 왼쪽 → X-Real-IP, 검증 없음)으로 바꾸면 resolver 9건 +
    미들웨어 2건 실패. `test_real_ip_is_used_only_without_forwarded_for`·`test_missing_peer_is_unknown`·음수 거부는
    옛 규칙에서도 통과(경계 고정용)
  - B2 — 미들웨어를 되돌리면 5건 실패(500 기록·마스킹·쿠키 이름·기본 조립·주입 결정기).
    `test_successful_request_is_logged_with_its_status`·`test_query_string_without_sensitive_keys_is_kept` 는 통과(회귀 방지용)
  - B3 — 서비스를 되돌리면 절단 2건 실패(SQLite 는 길이를 강제하지 않아 긴 값이 그대로 저장된다)
  - B4 — 스키마 5개를 되돌리면 17건 실패. blog `test_patch_with_explicit_null_on_required_field_is_422` 는 B5 의
    NOT NULL→422 변환만으로도 통과한다 — 스키마와 Repository 를 **함께** 되돌리면 409 DUPLICATE 로 실패(두 겹 방어)
  - B5 — Repository·엔진 6개 파일을 되돌리면 `test_db_errors.py` 8건 실패(NOT NULL·FK·Raw 중복·기능 쿼리·직접 호출·
    로그 2·hide_parameters). 변환 표 단위 테스트 11건은 새 모듈 자체를 시험해 되돌림과 무관,
    `test_sqlite_unique_is_duplicate` 는 옛 코드도 통과(회귀 방지용)
  - B6 — 서비스를 되돌리면 날짜 범위 3건 실패(`9999-12-31` 은 overflow 500)
  - B7 — `main.py` 를 되돌리면 4xx 3건 실패(ERROR 로 찍혔다). 5xx ERROR 1건은 옛 코드도 통과
- **기존 테스트 영향:** 없음 — 기존 666건이 수정 없이 통과했다(`DuplicateException` 을 기대하던 테스트는 모두 UNIQUE 위반)
- **수렴 판정:** `CONVERGED` (Open Fix 0 — 단계 B 범위)
- **잔여 위험 변화:** R-010 추가(SQLite 외래 키 방향 미구분)
- **실행 환경 주석:** Round 1 과 같다 — mypy 는 같은 버전(1.20.2) 순수 Python 빌드를 `PYTHONPATH` 로 앞세워
  실행(게이트도 같은 방식), uvicorn 수명주기 3건은 저장소 밖 fakeredis TCP 서버(127.0.0.1:6379)로 돌리고 종료했다

### Round 3 — 2026-10-12 · 단계 C (base SHA: `243f7ae`, 커밋 `ba7bc19`~`ed618df`)
- **트리거:** 사용자 요청 REQ-001 (제안 6)
- **검수 범위:** `app.dependency_overrides` 로 세션 의존성을 바꾸는 테스트 전수(기능 8개 + `tests/` 1개 — 10개 파일),
  MySQL 통합 하네스(`tests/integration/conftest.py`)와 CI `mysql` job, C2 대상 경로(catalog 서비스·`BaseRepository.list`·
  `DatabaseErrorTranslator`·home `fit_to_columns`)
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 ☑ 5 ☑ — `pytest -m "not mysql"` **746 passed · 13 deselected · skipped 0**,
  ruff check·format 그린, mypy 191 파일 무결(`tests/` 는 mypy 제외 설정), `review_gate --fast` 전건 통과(ENV=test),
  `-m mysql` 13건 수집(기존 8 + 스모크 5)
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 2 · LOW 0 (F-014·F-015)
- **신규 Fix(계약 위반):** F-014 · F-015, 전부 Fixed
- **결정:** 헬퍼는 픽스처가 아니라 함수 `override_db_sessions(app, maker, on_session=None)` 다 — 기능마다 테스트 DB
  (시드·엔진 수명)가 달라 maker 는 호출자가 만들고, commit 횟수 집계처럼 세션을 감싸는 일은 `on_session` 콜백으로
  받는다. 두 의존성이 이제 **서로 다른 세션**을 받는다(운영과 같다) — 집계 테스트는 카운터를 공유하므로 의미가 그대로다.
  C3(설정 reload 순서 의존)는 이 저장소에 해당 코드가 없어 하지 않았다
- **fail-on-revert:** 대상 파일을 저장소 밖에 복사해 두고 되돌린 뒤 복사본으로 복원했다.
  - C1 — 헬퍼에서 `mark_read_only` 를 빼면 `test_get_route_writing_through_read_only_override_is_rejected` 실패
    (`DID NOT RAISE ReadOnlyRoutingError`). blog `test_endpoint.py` 를 옛 내용으로 되돌리면
    `test_tests_do_not_hand_roll_session_overrides` 실패. `test_writer_override_session_can_write` 는 옛 방식에서도
    통과한다(쓰기 경로 회귀 방지용)
  - C2 — MySQL 이 로컬에 없어 실행하지 못했다(작성·수집만). CI `mysql` job 이 `--mysql-required` 로 돌리므로 skip 될 수 없다.
    collation 테스트는 전제(`utf8mb4_unicode_ci`, compose.test.yaml 의 서버 설정)를 먼저 단언한다
- **기존 테스트 영향:** 전환한 10개 파일의 기존 테스트가 표시된 세션에서도 모두 통과했다 — GET 경로의 숨은 쓰기는 없었다
- **수렴 판정:** `CONVERGED` (Open Fix 0 — 단계 C 범위. C2 의 실제 실행 근거는 CI `mysql` job)
- **잔여 위험 변화:** 없음
- **실행 환경 주석:** Round 1 과 같다 — mypy 는 같은 버전(1.20.2) 순수 Python 빌드를 격리 환경에서 실행했고, uvicorn
  수명주기 3건은 저장소 밖 fakeredis TCP 서버(127.0.0.1:6379)로 돌리고 종료했다

### Round 4 — 2026-10-12 · 단계 D (base SHA: `2cd4def`, 커밋 `af55c67`)
- **트리거:** 사용자 요청 REQ-001 (제안 7)
- **검수 범위:** 시각 컬럼 전수(metadata 13개 — `type_annotation_map`·두 Mixin·`generated_at`), 시각 생성 지점
  (`timezone_settings.now()` 호출처 3곳 → `utc_now()`), Raw 시각 바인드(리포트 조회·적재), Alembic 비교·렌더 경로
  (`migrations/env.py` online·offline), Celery 설정, 응답 스키마의 시각 설명(blog·reply·sns·user·catalog·home·reports)
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 ☑ 5 ☑ — `pytest -m "not mysql"` **769 passed · 16 deselected · skipped 0**,
  ruff check·format 그린, mypy 192 파일 무결, `review_gate --fast` 전건 통과(ENV=test), `-m mysql` 16건 수집,
  `alembic heads` 단일 head(`a7c9e1f3b5d6`), 임시 SQLite 파일에 `upgrade head` → `alembic check`("No new upgrade
  operations detected") → `downgrade e5f7a9b1c4d5` 성공, MySQL 리비전 SQL 은 `--sql`(offline)로 렌더해 검토
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0 (기존 F-016 을 닫았다)
- **신규 Fix(계약 위반):** F-016 Fixed
- **결정:** ADR-023(Alembic 훅·방언별 로컬 일자 식·Raw 시각 바인드 타입·리비전 방언 판정·"(UTC)" 설명 확장)
- **fail-on-revert:** 대상 파일을 저장소 밖에 복사해 두고 되돌리거나 변이를 넣은 뒤 복사본으로 복원했다.
  - D1 — `models_base.py` 를 `main` 내용으로 되돌리면 9건 실패(`test_model_default_is_aware_utc`·스냅샷 2건·catalog
    오프셋·리포트 5건 — naive 시드가 UTC 로 해석되며 날짜가 밀린다). `UTCDateTime` 이 naive 를 받게 바꾸면
    `test_bind_rejects_naive`·`test_raw_repository_rejects_naive_bounds` 실패. 비교 훅의 fsp 판정을 빼면
    `test_compare_type_flags_mysql_datetime_without_microseconds` 실패. `env.py` 를 되돌리면
    `test_alembic_check_reports_no_drift_through_env` 실패(훅이 `configure` 에 넘어가지 않는다)
  - D3 — 리포트 일자 식을 UTC 날짜(`DATE(o.created_at)`)로, 경계를 UTC 자정으로, Raw 바인드에서 타입을 빼는 변이
    각각에서 `test_order_after_local_midnight_counts_for_the_next_local_day` 실패(타입 제거는 naive 거부 테스트도 실패).
    `generated_at` 을 `now()` 로 되돌리면 `test_snapshot_generated_at_is_rendered_as_utc` 실패(`+09:00`)
  - D4 — `app/celery/app.py` 를 되돌리면 `test_celery_uses_utc_internally` 실패
  - `test_local_day_bounds_*`·`test_offset_param_*` 는 새 함수 자체를 시험한다(되돌리면 import 실패). MySQL 3건
    (`test_datetime6_roundtrip_*`·`test_order_after_local_midnight_*_on_mysql`·`test_utc_revision_converts_existing_kst_values`)은
    로컬에 MySQL 이 없어 작성·수집만 했다 — CI `mysql` job 이 `--mysql-required` 로 실행한다
- **기존 테스트 영향(골든 갱신 · 이유):**
  - `tests/core/schema_snapshot.json` — 시각 컬럼 13개의 `timezone` 이 `true → false`. impl 이 `DateTime()` 이라서다 —
    `timezone=True` 플래그는 MySQL·SQLite 에서 아무 일도 하지 않았고(검수 R-05), 시간대 처리는 이제 타입이 한다.
    그 밖의 지문(이름·순서·nullable·default·index·comment)은 그대로다
  - `test_timestamp_columns_are_timezone_aware` → `test_timestamp_columns_are_stored_as_utc` — 기준을 무의미해진 플래그에서
    `UTCDateTime` 타입으로 바꿨다(약화가 아니라 강화 — 모든 `_at` 컬럼이 naive 거부·UTC 변환을 강제받는지 본다)
  - 리포트 SQLite·MySQL 시드와 Repository 직접 호출, MySQL ORM 스모크의 동률 시각을 aware 로 바꿨다(naive 는 이제
    저장 경로에서 거부된다). 시드 값은 로컬(TIME_ZONE) 벽시계 그대로라 기대 결과는 바뀌지 않았다
  - `tests/test_response_serialization.py` 의 바이트 고정은 바꾸지 않았다 — aware UTC 는 원래 `Z` 로 고정돼 있고, 모델
    값이 그 경로를 타게 됐을 뿐이다. 응답 오프셋은 catalog·reports 엔드포인트 테스트가 따로 본다
  - MySQL 스키마 비교(`test_migrated_mysql_schema_matches_models`)에 env.py 와 같은 `compare_type` 훅을 넘긴다 —
    기본 비교로는 `DATETIME(6)` 누락을 못 잡는다
- **수렴 판정:** `CONVERGED` (Open Fix 0 — 단계 D 범위. MySQL 실행 근거는 CI `mysql` job)
- **잔여 위험 변화:** R-011 추가(리비전의 +09:00 가정, SQLite 기존 값 미변환). R-003(고정 오프셋)은 코드에 `ponytail:`
  주석으로 위치를 남겼다
- **실행 환경 주석:** Round 1 과 같다 — mypy 는 같은 버전(1.20.2) 순수 Python 빌드를 격리 환경에서 실행했고, uvicorn
  수명주기 3건은 저장소 밖 fakeredis TCP 서버(127.0.0.1:6379)로 돌리고 종료했다. `review_gate` 의 네트워크 단계(pip-audit)는
  `--fast` 에서 돌지 않는다

### Round 5 — 2026-10-12 · 단계 E (base SHA: `6e19cd1`, 커밋 `a902f89`)
- **트리거:** 사용자 요청 REQ-001 (제안 8, "redis 필수")
- **검수 범위:** Redis client 소유·소비 경로(`resources._redis` → `app.state.redis`, 소비처 0건이던 것), `/ready` 판정·로그,
  Celery 앱 include·모델 등록·태스크 모듈 전수(중앙 `app/celery/tasks.py` 1건), 기능 패키지 탐색(`models_registry`),
  home 조립 경로(HTTP provider·태스크), `compose.test.yaml` 의 `redis-test`(이미 있음 — 확인만)
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 ☑ 5 ☑ — `pytest -m "not mysql"` **783 passed · 16 deselected · skipped 0**,
  ruff check·format 그린, mypy 193 파일 무결, `review_gate --fast` 의 구조 검사 전건 통과(ENV=test — mypy 단계만 `.venv` 의
  컴파일 DLL 이 앱 제어 정책에 막혀 FAIL, 같은 버전 순수 Python 빌드로 따로 돌려 그린), `-m mysql` 16건 수집
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0 (기존 F-017·F-018 을 닫았다)
- **신규 Fix(계약 위반):** F-017·F-018 Fixed
- **결정:** ADR-024(`get_redis` 위치·503, `/ready` 동시 판정·로그 범위, `find_spec` 기반 태스크 발견, 공용 조립 함수)
- **fail-on-revert:** 대상 파일을 저장소 밖에 복사해 두고 되돌리거나 변이를 넣은 뒤 복사본으로 복원했다.
  - E1 — `main.py` 를 `main` 내용으로 되돌리면 6건 실패(Redis ping 확인·ping 실패·timeout·동시성·client 없음·로그).
    `get_redis` 가 raise 대신 `None` 을 돌려주면 `test_get_redis_without_client_is_503` 2건 실패. `gather` 를 순차 await 로
    바꾸면 `test_ready_checks_database_and_redis_concurrently` 실패. 로그 인자를 `str(exc)` 로 바꾸면
    `test_ready_logs_only_target_and_exception_type` 실패. `test_get_redis_returns_the_lifespan_client` 는 새 provider
    자체를 시험한다(되돌리면 import 실패)
  - E2 — `app/celery/app.py`·`app/celery/tasks.py` 를 `main` 내용으로 되돌리면 4건 실패(include 계약 2·AST·태스크 provider).
    태스크 본문이 `UserAccessLogService` 를 직접 만들면 `test_task_builds_service_through_home_provider` 실패. 탐색이
    `find_spec` 대신 `import_module` 을 쓰면 4건 실패(태스크 모듈을 import 해 터진다). `test_discovery_lists_home_tasks`·
    `test_aggregate_task_registered_through_discovery` 는 새 함수·새 위치를 시험한다(되돌리면 import 실패)
- **기존 테스트 영향:** `tests/core/test_celery_app.py` 의 `"app.celery.tasks" in include` 단언을 "include == 탐색 결과,
  전부 `app.features.*`" 로 바꿨다(중앙 모듈이 사라졌으므로). `app/features/home/tests/test_home_tasks.py` 는 중앙 모듈 import
  대신 Celery 의 include import(`loader.import_default_modules()`)로 등록을 확인한다. `tests/test_health_ready.py` 의 기존
  DB 실패·timeout·원문 비노출 테스트는 그대로 두고, client fixture 가 `get_redis` 를 가짜로 바꿔 끼운다
  (`test_ready_returns_200_when_database_answers` → `..._and_redis_answer` 로 이름과 단언을 넓혔다)
- **문서 갱신:** README(기술 표·`/ready`·Redis 환경 변수), ARCHITECTURE(§1 구조·의존 규칙, §3.4 `/ready`, §7.2 `get_redis`,
  §13 Celery 발견·기능 제거 시 동작·provider 재사용, 설계 결정 표), DEVELOPMENT(§3 Redis 의존성, §10.3 기능별 태스크)
- **charter §3 C 정정:** Round 3 에서 단계 C 를 끝내고도 인수 기준 체크를 빠뜨렸다. F-014·F-015 Fixed 와 CI run
  `38208514130`(`2cd4def`, 단계 C 병합 — `MySQL 8.4 통합` job `pytest -m mysql --mysql-required` 13 passed, `GATE 3` job
  746 passed·skip 0)을 근거로 닫았다
- **수렴 판정:** `CONVERGED` (Open Fix 0 — 단계 E 범위)
- **잔여 위험 변화:** 없음(R-005 fail-closed 는 그대로 — 이제 `/ready` 도 Redis 장애에 503 을 낸다는 것이 그 내용이다)
- **실행 환경 주석:** Round 1 과 같다 — mypy 는 같은 버전(1.20.2) 순수 Python 빌드를 격리 환경에서 실행했고, uvicorn
  수명주기 3건은 저장소 밖 fakeredis TCP 서버(127.0.0.1:6379)로 돌리고 종료했다

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 3 | 2 | 5 | CONVERGED (단계 A) |
| 2 | 0 | 1 | 5 | 3 | 9 | CONVERGED (단계 B) |
| 3 | 0 | 0 | 2 | 0 | 2 | CONVERGED (단계 C) |
| 4 | 0 | 0 | 0 | 0 | 1 (F-016) | CONVERGED (단계 D) |
| 5 | 0 | 0 | 0 | 0 | 2 (F-017·F-018) | CONVERGED (단계 E) |
