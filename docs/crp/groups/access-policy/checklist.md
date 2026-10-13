# Checklist — access-policy (개선 항목 추적판)

> 모든 개선 사항은 여기서 추적된다. 각 항목이 닫히기(`[x]`) 전엔 "완료" 가 아니다. ledger 의 Fix 와 1:1 로 연결한다.

## Round 1 — 2026-10-13 · 원 명세 (뷰 단위 접근 수준 · 기동 시 기본 거부 · 테스트 정리)
- [x] 요청을 design-baseline §2 에 기록(REQ-001 A~D), 선행 그룹 제약 확인(C-3)
- [x] 변경 전 OpenAPI 를 정렬 JSON 으로 저장(불변 비교 기준)
- [x] (F-001) `access.py` — 접근 수준 4개 + `AccessPolicyGuard` + `AccessPolicyError`, 가드 단위 테스트 16건
- [x] `main.py` 조립 끝 `verify(app)` + 별도 프로세스 기동 실패 테스트
- [x] 예시 뷰 전부 뷰 단위 선언(home·reports 라우터 단위 의존성 → 뷰), OpenAPI 바이트 동일 확인
- [x] (F-002) `EXPECTED_ACCESS` 단일 표 + 판정 대조, `ADMIN_ROUTES` 제거·표에서 401/403 대상 도출, `OWNED` 대상 집합 검사
- [x] README·ARCHITECTURE(§7.1·§7.3·§11.1·§11.2)·DEVELOPMENT(§2·§3.1·§5.5·§6.6·§13)·관리 인증 안내서·기능 개발 안내서
- [x] 공통 게이트 그린 · fail-on-revert · run-log 갱신

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
