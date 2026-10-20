# Checklist — integration-e2e (개선 항목 추적판)

> 모든 개선 사항은 여기서 추적된다. 각 항목이 닫히기(`[x]`) 전엔 "완료" 가 아니다. ledger 의 Fix 와 1:1 로 연결한다.

## Round 1 — 2026-10-20 · 계획서 W0~W9 · L1~L6
- [x] 요청을 design-baseline §2 에 기록(REQ-001~006)
- [x] 병합된 main(`292ba5b`)에서 인벤토리 재추출 — run-log
- [x] (F-001) W0 — Redis 대상 명시 강제·자식 env 고정·CI 변수, fail-on-revert, 별도 커밋
- [x] (F-002) L1 에서 찾은 환경 의존 테스트 고정, 별도 커밋
- [x] W1 `compose.e2e.yaml` — primary + GTID replica + Redis 7.4, tmpfs, 127.0.0.1 고정 포트
- [x] W2 하네스 — 점유·대상 검사, 실행마다 비밀값, 복제 부착, Alembic·슈퍼유저, uvicorn·worker, keepalive, 로그 수집
- [x] W3 인벤토리 대조기 `test_zz_inventory.py`
- [x] W4 L1~L6 테스트
- [x] W5 dev 의존성 `playwright`, 마커 `e2e`
- [x] W6 CI job `e2e`
- [x] W7 README·DEVELOPMENT·ARCHITECTURE·CRP 6파일, `review_gate` 요구 ID 출처
- [x] W9 `docs/review` 병합 표에 "병합 대기" 덧붙임(커밋하지 않음)
- [ ] (F-003) 프로세스 파일에 import 중 줄이 빠짐 — **결정 필요**(보고)
- [ ] (F-004) Redis 장애 시 API 500·연결 종료 — **결정 필요**(보고)
- [ ] (R-004) replica 장애 시 읽기 실패·`/ready` 200 — **결정 필요**(보고)
