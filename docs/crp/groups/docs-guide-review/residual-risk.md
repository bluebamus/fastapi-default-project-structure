# Residual Risk — docs-guide-review (잔여 위험 등록부)

> 코드와 문서를 다시 대조한 결과입니다. 해결된 항목은 재검수 근거와 함께 아래에 보존합니다.

## 남은 위험

| ID | 항목 | Severity | 미검증 사유 | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-003 | 실제 프로세스가 필요한 동작(503 실응답·keep-alive·종료 예산), sqladmin 화면별 요청 방식, 저장소 밖 통계는 이번 정적·단위 검수에서 확인하지 않았다 | LOW | 외부 DB·Redis·브라우저를 포함한 운영형 E2E 범위 | 2026-10-21 | CI 또는 실환경 E2E 결과와 대조할 때 |

## 해결된 후속 항목

| ID | 해결 내용 | 근거 |
|---|---|---|
| R-001 | `main.run_server` docstring을 실제 `adopt_foreign_handlers` 동작과 일치하도록 수정했다 | `main.py`의 현재 docstring, commit `8cb0438` |
| R-002 | 코드의 오래된 `e2e-policy-2 결정 N` 인용을 제거·정리했다 | 현재 Python 소스 검색 결과 0건, commit `8cb0438` |
