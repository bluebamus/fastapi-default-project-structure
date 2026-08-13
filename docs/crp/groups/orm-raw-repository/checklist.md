# Checklist — <그룹 이름> (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. 라운드 시작 시 이번 할 일을 적고, GATE 진행에 따라 체크한다. ledger 의 Fix 항목과
> 1:1 로 연결한다(개선 = ledger Fix; 하드닝은 residual-risk 로 가므로 여기 두지 않는다).

## Round N — YYYY-MM-DD
- [ ] 이번 요청을 design-baseline §2(요구사항 레지스터)에 기록 + 이전 요구 충돌 확인
- [ ] (ledger F-___) <개선 항목 요약> — 회귀 테스트 추가 · fail-on-revert 검증(타깃 플랫폼)
- [ ] GATE 3 인수기준 전부 그린(진입점 매트릭스 포함)
- [ ] 요구사항 회귀 0 — design-baseline Active 요구·불가침 제약 위반 없음 확인
- [ ] run-log 심각도 추세 갱신 + 수렴 판정 기록
- [ ] residual-risk 갱신(이번에 수용한 하드닝/by-design)

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
