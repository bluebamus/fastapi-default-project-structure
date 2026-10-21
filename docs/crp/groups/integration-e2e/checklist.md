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
- [x] (F-003) 프로세스 파일에 import 중 줄이 빠짐 — **결정 필요**(보고) → Round 2 에서 사용자 결정으로 해결
- [x] (F-004) Redis 장애 시 API 500·연결 종료 — **결정 필요**(보고) → Round 2 에서 사용자 결정으로 해결
- [x] (R-004) replica 장애 시 읽기 실패·`/ready` 200 — **결정 필요**(보고) → Round 2 에서 사용자 결정으로 해결

## Round 2 — 2026-10-20 · 사용자 결정 반영(F-004·R-004·F-003)
- [x] 결정을 design-baseline 에 기록(REQ-007, ADR-009~011), logging-overhaul ADR-002 판정 시점 부분 Superseded
- [x] (F-004) Redis 연결 오류 → 503 `SERVICE_UNAVAILABLE`, traceback 한 번, keep-alive 유지 — 단위·e2e 테스트, fail-on-revert, `9cff14c`
- [x] (R-004) 읽기 전용 세션의 replica 연결 오류 → primary 한 번 재시도 + WARNING — 단위·e2e 테스트, fail-on-revert, `a8be33a`
- [x] (F-003) 설정 로드 직후 프로세스 파일 부착 — 단위(실행 경로 5종)·e2e 테스트, fail-on-revert, `3d30859`
- [x] README·ARCHITECTURE 장애 동작 설명을 실제 동작으로
- [x] Round 1 의 결정 필요 3건 닫음 — F-003·F-004 Fixed(ledger), R-004 해소(residual-risk)

## Round 3 — 2026-10-21 · e2e 정책 결정 2차(결정 1~7, 브랜치 `fix/e2e-policy-2`)
- [x] 결정을 design-baseline 에 기록(REQ-008, ADR-012~016)
- [x] 결정마다 해당 여부 확인 — 고침 1·2·3·5·7, 이미 충족 6, 해당 없음 4(결정 2 는 보류 뒤 확정)
- [x] (F-008) 422 문서 = `ErrorResponse` — 계약 테스트, fail-on-revert, `01f1d6a`·`6f479c4`
- [x] (F-009) 모든 401 에 `WWW-Authenticate: Bearer` — 단위·e2e, fail-on-revert, `98c390d`
- [x] (F-010) 인증 사용자 조회 primary — 단위·e2e(복제 지연), fail-on-revert, `db1d3fe`
- [x] 결정 6 계약 고정(쿠키 없는 첫 요청 503) — 단위·e2e, 변이 검증, `cce4fdd`
- [x] (F-011) CSRF 상한 413·400 — 단위·e2e(L5 측정 갱신, RSS), fail-on-revert, `8f3d269`
- [x] (F-012) 결정 2 — 가장 바깥 사용자 미들웨어, 단위·실제 uvicorn, fail-on-revert, `0fef02e`
- [x] 의존성 `aiomysql[rsa]` 통일(ADR-017) — 계약 테스트, fail-on-revert, lock 표기만 변경, `9774d68`
- [x] README·ARCHITECTURE·관리 화면 안내서 설명을 실제 동작으로
- [x] `docs/review` 병합 표에 certifi 병합과 이번 브랜치(병합 대기) 덧붙임(커밋하지 않음)
