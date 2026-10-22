# Run Log — docs-guide-site (라운드 로그 + 수렴 판정)

작업 기준선 base SHA: `e4806f6` (main). 브랜치 `docs/guide-site`.

## 라운드 기록

### Round 1 — 2026-10-22 · 생성 가이드 사이트 검수 반영
- **트리거:** REQ-001 — 2차 검수 42건(HIGH 2: FEA-01·TST-01)
- **재확인:** `main.py`(미들웨어 등록 순서·`unhandled_exception_middleware`·`openapi_url`·`AccessPolicyGuard`), `config.py`(검사 3종·`REQUIRED_WITHOUT_ENV_FILE`·Settings 9종 69 필드),
  `app/core/resources.py`, `app/core/db/session.py`, `app/core/security/` 전반, `app/features/auth/` 전반, `app/features/home/tasks.py`, `app/features/reports/api/routers/v1/sales_reports.py`,
  `app/core/db/models_registry.py`, `app/features/admin.py`, `tests/core/test_layering.py`, `app/core/redis.py`(`get_redis` 소비처). 지적과 다르게 고친 것 1(OPS-02).
- **계약 테스트:** `tests/test_docs_guide_site.py` — 생성 원본에서 4 failed(API 표 접근 수준 열 없음·설정 30개 누락·mermaid@11 19편·허브 미링크 9편), 수정 후 전부 통과
- **검사:** `.env` 없는 클론에서 `tests/test_doc*.py` 통과, ruff check·format --check 통과, 링크·앵커 broken 0(README `Argon2id` 오탐 제외), HTML 파싱 오류 0, 공통 결함 표지 0
- **커밋:** `b439092` 원본 · `ccdd874` 흐름 · `c3d8396` 시작·설정·API·배포 · `ea2fd46` 기능·개발·테스트 · `370b51b` 허브·공통 · `b241acc` 코드 docstring · `b0cb53b` 계약 테스트 · `6195d85` 재검 반영
- **잔여:** R-001~R-003
- **수렴 판정:** `CONVERGED`
