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

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 3 | 2 | 5 | CONVERGED (단계 A) |
| 2 | 0 | 1 | 5 | 3 | 9 | CONVERGED (단계 B) |
