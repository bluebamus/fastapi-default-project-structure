# Ledger — followups-2026-11 (결함 원장)

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | INV-1 | Fix | Fixed | `fix/coverage-omit` 병합 | `cwd=tmp_path` subprocess 테스트의 자식 coverage 가 설정을 못 찾아 omit 없이 `app/` 미실행 파일을 touch → 테스트 22개(1211 stmts)·`__init__` 가 TOTAL 에 섞임. Windows 경로 문제가 아니다(GlobMatcher 는 일치) |
| F-002 | LOW | INV-2 | Fix | Fixed | `fix/log-test-isolation` 병합 | `test_migrations` 가 env.py `fileConfig` 로 root 핸들러를 갈아끼워 뒤 테스트 전부의 로깅 구성을 바꿈 |
| F-003 | LOW | INV-2 | Fix | Fixed | `fix/log-test-isolation` 병합 | debug 상세 테스트가 root `RedactingFilter` 가 가린 `exc_text` 를 판정 — F-002 오염 덕에만 통과 |
