# Residual Risk — docs-guide-review (잔여 위험 등록부)

> 의도적으로 고치지 않은 것. 고쳐야 하면 새 결함이 아니라 범위 변경 — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가 | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | `main.run_server` docstring 이 "`uvicorn main:app` CLI 면 uvicorn 기본 포맷" 이라고 적는다 — 문서(F15)와 코드 동작(`adopt_foreign_handlers`)은 "같은 포맷" | LOW | 코드 파일은 이 그룹 범위 밖(C-1 — 문서만 고친다) | 2026-10-21 | 다음에 `main.py` 를 고치는 작업에서 docstring 한 줄 |
| R-002 | 코드 주석·docstring 의 "e2e-policy-2 결정 N" 인용(`main.py` 등)은 그대로다 — 가이드 문서만 ADR 번호로 바꿨다(F27) | LOW | 같은 이유(C-1) | 2026-10-21 | 같은 파일을 고칠 때 |
| R-003 | 실행해야 아는 동작(503 실응답·keep-alive·종료 예산)·sqladmin 화면별 요청 방식·저장소 밖 통계는 검수 보고의 UNVERIFIED 3건으로 남는다 | LOW | 서버·DB·Redis 실행 금지 | 2026-10-21 | CI e2e 결과로 대조할 때 |

## 후속 기록 (2026-10-22 추가 — 위 행은 고치지 않는다)

| ID | 상태 | 근거 |
|---|---|---|
| R-001 | 해소 — `main.run_server` docstring 을 실제 동작(CLI 도 같은 포맷)으로 고쳤다 | commit `8cb0438` |
| R-002 | 해소 — 코드의 `e2e-policy-2 결정 N` 인용을 integration-e2e ADR 번호로 바꿨다(현재 Python 소스 0건) | commit `8cb0438` |
| R-003 | 유지 | — |
