# Residual Risk — admin-session-hardening (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용"으로 박제된 항목은 의도적으로 고치지 않기로 한 것이다. 고쳐야 하면 새 결함이 아니라
> **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | JS 를 끈 브라우저에서는 관리 화면의 생성·수정·삭제·로그아웃이 403/405 다 — 토큰을 붙이는 것이 인라인 스크립트다 | LOW | ADR-004. sqladmin 의 삭제 모달·일괄 삭제·import 도 원래 JS 가 필요하다. 미사용 만료(30분)가 로그아웃을 대신한다 | 2026-10-19 | JS 없는 관리 화면이 요구되면 — create/edit 템플릿을 덮어써 hidden 필드를 서버에서 그리고, 로그아웃을 폼 버튼으로 |
| R-002 | sqladmin `@action`(사용자 정의 일괄 작업)은 GET(`window.location`)으로 상태를 바꾸므로 CSRF 미들웨어가 보지 않는다 — 지금은 등록된 것이 없다 | LOW | ADR-004, C-3. `test_no_view_registers_a_custom_get_action` 이 등록을 막는다 | 2026-10-19 | action 이 필요해지면 — POST 엔드포인트로 감싸고 스크립트가 토큰을 싣게 한다 |
| R-003 | 관리 세션이 Redis 에만 있다 — Redis 장애 중 관리 화면은 503, 데이터 삭제(`FLUSHDB`)·키 교체는 모든 관리자를 로그아웃시킨다. Redis 자체가 침해되면 세션 내용(`user_id`·CSRF 토큰)이 보인다(쿠키는 HMAC 키라 못 만든다) | LOW | ADR-001, C-2. Redis 필수 정책(service-hardening R-005)과 같다 | 2026-10-19 | 관리 화면의 가용성이 Redis 와 분리돼야 하면 |
| R-004 | 관리 화면에서 사용자를 비활성화·삭제해도 그 사용자의 **API refresh 토큰**은 폐기되지 않는다(관리 세션만 폐기). API 경로(`UserService`)는 둘 다 폐기한다 | LOW | 명세 §1 범위는 관리 세션 폐기다. 관리 화면의 sqladmin 저장 경로는 `UserService` 를 거치지 않는 기존 구조다 | 2026-10-19 | 관리 화면이 주된 계정 관리 수단이 되면 — `UserAdmin` 훅에서 refresh `revoke_user` 도 부른다 |
| R-005 | 실기동 스모크는 SQLite 파일 DB·fakeredis TCP 로 관리 화면만 조립한 런처로 돌렸다(앱 엔진은 MySQL URL 로만 만들어진다). 브라우저 스크립트는 노드에서 DOM 스텁으로 동작을 확인했다(실제 브라우저 아님) | LOW | 저장소 규칙상 로컬 MySQL·docker 를 쓰지 않는다. MySQL 로그인·POST 로그아웃은 `mysql` 마커 테스트로 CI 가 돈다 | 2026-10-19 | CI 의 MySQL job 이 실패하거나 실제 브라우저에서 토큰이 붙지 않는 사례가 나오면 — browser 마커 테스트 추가 |
| R-006 | API 에는 비밀번호 변경 경로가 없다. 관리 화면 훅은 `data` 의 `hashed_password` 변경을 폐기 조건으로 보지만, 관리 폼은 비밀번호를 다루지 않아(`hashed_password` 제외) 지금은 훅 단위 테스트로만 확인된다 | LOW | ADR-002·ADR-007 | 2026-10-19 | 비밀번호 변경 기능을 만들 때 — API 는 `UserService` 에서 refresh·관리 세션을 함께 폐기, 관리 폼에 필드를 더하면 화면 테스트로 확인 |
| R-007 | 관리 화면에서 **자기 자신**을 강등·비활성화하면 지금 쓰는 세션도 바로 끊긴다(저장은 되고 다음 요청이 로그인 화면) | LOW | ADR-007 — 감독자 지시 "그대로 둔다(문서화)". 권한을 잃은 세션을 남기지 않는 쪽이 일관된다 | 2026-10-19 | 자기 강등 실수가 잦으면 — 확인 대화상자 또는 마지막 슈퍼유저 강등 거부 |

> R-004 상태(2026-10-19): **해소** — 이 그룹 F-006(ADR-008, 브랜치 `fix/admin-ui-refresh-revoke`). 관리 화면에서 비활성화·슈퍼유저 해제·비밀번호 해시 변경·삭제하면 `UserAdmin` 이 커밋 전에 `RefreshTokenStore.revoke_user` 와 `AdminSessionStore.revoke_user` 를 함께 부른다. 어느 쪽이든 실패하면 변경이 저장되지 않는다.
