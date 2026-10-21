# Run Log — docs-guide-review (라운드 로그 + 수렴 판정)

작업 기준선 base SHA: `6eff7a2` (main). 브랜치 `docs/guide-fixes`.

## 라운드 기록

### Round 1 — 2026-10-21 · 안내서 검수 반영
- **트리거:** REQ-001 — 검수 보고 29건(HIGH 2 · MED 9 · LOW 18) + 누락 5건, README 같은 사실
- **재확인:** 지적마다 코드 근거를 다시 열었다 — `main.py`(미들웨어·처리기 등록 순서, `readiness_check`, `_openapi_with_actual_422`,
  `AccessPolicyGuard`), `app/utils/logs/setup.py`(`entry_process`·`attach_log_files`), `app/core/repositories/db_errors.py`,
  `app/core/schemas.py`, `app/core/db/router.py`, `app/celery/app.py`, `app/core/security/admin_session.py`,
  `app/features/auth/admin_backend.py`, `config.py`(클래스 9개·`LOG_SECRET_SETTINGS`), `migrations/versions/`(head `c9e1a3b5d7f0`),
  `tests/integration/test_uvicorn_lifecycle.py`, `.github/workflows/ci.yml`. `ENV=test` 로 `app.openapi()` 를 세어 24 경로 / 39 오퍼레이션.
  틀린 지적 0.
- **README:** 처음부터 끝까지 읽고 같은 사실 5곳(파일 로그·Redis 소비처 2곳·수명 테스트 실패/skip·CLI 로그 포맷)을 고쳤다.
  새 종류의 검수는 하지 않았다.
- **검사:** `tests/test_docs_guides.py`·`tests/test_docs_secret_examples.py` 11 passed · 링크·앵커 broken 0(README `Argon2id` 오탐 1건 제외) ·
  HTML 4편 `html.parser` 태그 불일치 0 · `git diff --ignore-cr-at-eol --stat` = `git diff --stat`(EOL 변화 0) ·
  `review_gate --fast` 전건 통과(pytest 제외 모드)
- **커밋:** `011efa8` HTML 3편 · `e6cbd3d` ARCHITECTURE·DEVELOPMENT · `0efc0a0` README
- **잔여:** R-001~R-003(코드 docstring 2건은 범위 밖, UNVERIFIED 3건)
- **수렴 판정:** `CONVERGED`
