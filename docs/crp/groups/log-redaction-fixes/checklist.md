# Checklist — log-redaction-fixes (개선 항목 추적판)

> 모든 개선 사항은 여기서 추적된다. 각 항목이 닫히기(`[x]`) 전엔 "완료" 가 아니다. ledger 의 Fix 와 1:1 로 연결한다.

## Round 1 — 2026-10-13 · 원 명세 (traceback 마스킹 · 접속 로그 유지 · 405 Allow · Redis 버전 · 보호 현황 조사)
- [x] 요청을 design-baseline §2 에 기록(REQ-001 A~E), 선행 그룹 제약 확인(C-4)
- [x] 재현 — 실제 dictConfig 로 stdout·stderr 에 비밀값이 남는 것을 확인
- [x] (F-001) `RedactingFilter`·`redact()` 정본 + queue 필터 + 경로별 테스트
- [x] (F-002) uvicorn CLI 로거·Celery 핸들러 부착 + 테스트
- [x] (F-003) DEBUG 500 `detail` 마스킹 + 테스트
- [x] 405 `Allow`·예외 헤더 확인(이미 정상, ADR-002) + 회귀 테스트, 헤더 전달 제거 변이로 실패 확인
- [x] (F-004) `REDIS_MIN_VERSION`=6.2 + 기동 확인 + 계약 테스트 + 문서 9곳
- [x] 접속 로그 원문 저장 — 코드·테스트 미변경, ADR-004·R-001 "결정으로 수용"
- [x] §5 엔드포인트 보호 조사(읽기 전용) — R-004, 보고
- [x] README·ARCHITECTURE·DEVELOPMENT·server-lifecycle 안내서 반영

## Round 2 — 2026-10-13 · 추가 명세 §8 (커버리지 하한 0%)
- [x] REQ-002·ADR-005 기록
- [x] (F-005) `fail_under = 0` 명시 + CI 측정 + 계약 테스트(수정 전 2건 실패, 명령줄 하한 변이 1건 실패)
- [x] README CI 절·DEVELOPMENT §12.3(올리는 법)
- [x] 공통 게이트 그린 · fail-on-revert · run-log 갱신

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
