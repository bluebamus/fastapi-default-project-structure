# Residual Risk — access-policy (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용"으로 박제된 항목은 의도적으로 고치지 않기로 한 것이다. 고쳐야 하면 새 결함이 아니라
> **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | 가드는 선언이 **있는지·모순이 없는지**만 본다. 새 뷰에 잘못된 수준(예: 관리 기능에 `Public`)을 고르면 막지 못한다 — 예시 뷰는 `EXPECTED_ACCESS` 가 고정하지만 새 뷰의 기대 수준은 사람이 그 표에 더해야 한다 | LOW | charter §2-2. 올바른 수준은 업무 판단이다. 선언이 코드에 드러나 리뷰에서 보인다 | 2026-10-13 | 역할이 늘어 수준 선택이 자주 틀리면 — 기능별 기본 수준·리뷰 게이트 |
| R-002 | `Mount`(`/admin`)와 WebSocket 라우트는 검사 대상이 아니다. `/admin` 은 SQLAdmin 의 세션 인증(admin-login)이 맡는다. WebSocket 은 지금 없다 | LOW | 명세 §2 제외 대상. `APIRoute` 만 FastAPI 의존성 트리를 가진다 | 2026-10-13 | WebSocket 엔드포인트가 생기면 — `APIWebSocketRoute` 도 대상에 넣는다 |
| R-003 | 판정은 FastAPI 0.141 의 `iter_route_contexts`(`_IncludedRouter` 펼침)에 기댄다. 문서화되지 않은 모듈 함수라 FastAPI 를 올리면 바뀔 수 있다 | LOW | ADR-003. 중첩 펼침·라우터 단위 인정·표 대조 테스트가 바뀌면 바로 실패한다(fail-on-revert 로 확인) | 2026-10-13 | FastAPI 업그레이드 시 — 테스트가 깨지면 그 버전의 펼침 API 로 `routes()` 하나만 고친다 |
| R-004 | 표식 함수 `public`·`public_write` 는 요청마다 한 번 await 된다(아무 일도 하지 않는 코루틴) | LOW | ADR-001. 동기 함수였다면 스레드풀을 탔다. 측정할 만한 비용이 아니다 | 2026-10-13 | 없음 |
