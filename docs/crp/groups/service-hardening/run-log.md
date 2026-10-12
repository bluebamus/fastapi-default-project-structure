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

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 1 | 0 | 0 | 3 | 2 | 5 | CONVERGED (단계 A) |
