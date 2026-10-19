# Residual Risk — security-ops-hardening (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용"으로 박제된 항목은 의도적으로 고치지 않기로 한 것이다. 고쳐야 하면 새 결함이 아니라
> **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | 로그인 **이후** sqladmin 이 그리는 생성·수정·삭제 폼과 GET `/admin/logout` 에는 CSRF 토큰이 없다 | LOW | 명세 §3 범위 밖 — sqladmin 이 그리는 폼이다. `admin_session` 쿠키가 `SameSite=Strict`·`Path=/admin` 이라 교차 사이트 요청에 세션이 실리지 않는 것이 1차 방어다(admin-login ADR-002) | 2026-10-19 | 같은 사이트의 다른 경로(하위 도메인 포함)에 사용자 콘텐츠가 올라오거나 `SameSite` 를 낮춰야 하면 — sqladmin 폼 템플릿을 덮어써 같은 토큰을 싣고 미들웨어로 모든 POST 를 대조 |
| R-002 | 보존 삭제는 **beat 가 떠 있어야** 돈다. beat 를 띄우지 않으면 접속 로그가 그대로 쌓이고, 둘 띄우면 같은 삭제가 두 번 돈다(결과는 같고 부하만 는다) | LOW | ADR-003. FastAPI 는 worker·beat 를 띄우지 않는다(ARCHITECTURE §13). README 체크리스트 11 이 배포 전에 확인시킨다 | 2026-10-19 | 운영에서 beat 누락이 관측되면 — `/ready` 나 기동 로그에 마지막 실행 시각 노출, 또는 단일 실행 잠금(Redis `SET NX`) |
| R-003 | 보존은 삭제뿐이다 — 보관(archive)·익명화 없이 지운다. 첫 배포에서 오래된 행이 많으면 첫 실행이 여러 배치를 돈다 | LOW | 명세 §2("지운 총 행 수를 돌려준다"). 배치마다 커밋해 잠금은 짧다 | 2026-10-19 | 감사 보관 요구가 생기면 — 지우기 전에 내보내는 단계를 서비스에 더한다 |
| R-004 | 날짜 필터의 "최근 7일·30일" 은 `이후(포함)` + 시작 날짜 링크다 — 한 필터에 범위(시작~끝)를 둘 다 걸 수 없다 | LOW | ADR-005. sqladmin 0.32 의 연산 필터는 값 하나·연산 하나를 쿼리 파라미터로 받는다 | 2026-10-19 | 기간 조회가 자주 필요하면 — 두 번째 파라미터(`<name>_to`)를 읽는 필터로 확장 |
| R-005 | MySQL 의 보존 삭제(`DELETE ... WHERE id IN`)·CSRF 를 실은 MySQL 로그인은 로컬에서 돌리지 않았다(수집만 확인) | LOW | 저장소 규칙상 로컬 MySQL·docker 를 쓰지 않는다. `mysql` 마커 테스트로 작성해 CI 가 돌린다 | 2026-10-19 | CI 의 MySQL job 이 실패하면 |

> R-001 상태(2026-10-19): **해소** — admin-session-hardening F-003. `/admin` 의 POST·PUT·PATCH·DELETE 전부(로그인·로그아웃 포함)를 `AdminCsrfMiddleware` 가 세션 토큰과 대조하고(헤더 `X-CSRF-Token` 또는 폼 `csrf_token`), 화면은 `base.html` 의 meta·인라인 스크립트가 토큰을 싣는다. 로그아웃은 POST 전용(GET 405). 남은 것: JS 를 끈 브라우저·sqladmin `@action` GET 은 admin-session-hardening R-001·R-002.
> R-004 상태(2026-10-19): **해소** — admin-session-hardening F-004. `LocalDateFilter` 의 `between`(기간, 양 끝 포함, 값 `YYYY-MM-DD~YYYY-MM-DD`, 한쪽만이면 열린 구간).
