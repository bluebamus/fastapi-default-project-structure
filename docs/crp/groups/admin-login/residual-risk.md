# Residual Risk — admin-login (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용"으로 박제된 항목은 의도적으로 고치지 않기로 한 것이다. 고쳐야 하면 새 결함이 아니라
> **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | 서버 쪽 세션 저장소·폐기 목록이 없다 — 로그아웃 전에 복사된 `admin_session` 쿠키는 서명이 유효한 동안(최대 8시간) 다시 쓸 수 있다 | LOW | ADR-002. 매 요청 DB 확인이 있어 그 계정이 활성 슈퍼유저인 동안에만 유효하다. 쿠키는 HttpOnly·Secure(배포)·SameSite=Strict·Path=/admin | 2026-10-12 | 관리 세션의 즉시 강제 종료가 요구되면 — Redis 세션 저장소 또는 사용자별 세션 세대 번호 |
| R-002 | 로그인 폼에 CSRF 토큰이 없다(로그인 CSRF — 피해자를 공격자 계정으로 로그인시키기) | LOW | ADR-003. 공격자 계정도 슈퍼유저여야 의미가 있고, 로그인 뒤 관리 요청은 SameSite=Strict 라 교차 사이트에서 세션이 실리지 않는다 | 2026-10-12 | 관리 화면에 일반 사용자 계정이 들어오게 되면 |
| R-003 | 로그인 화면의 Bootstrap CSS 를 CDN(jsDelivr)에서 받는다 — 막힌 망에서는 스타일 없이 보인다 | LOW | ADR-003. 기능은 동작하고 SRI 가 변조를 막는다. 정적 파일 서빙을 새로 두지 않는다 | 2026-10-12 | 폐쇄망 배포가 생기면 — 정적 파일로 두고 SRI 대신 파일 해시를 고정 |
| R-004 | 예전 설정 `ADMIN` 이 남은 로컬 `.env`·배포 환경 변수는 갱신 전까지 기동이 멈춘다(ENV=test 는 제외) | LOW | ADR-005. 뜻이 뒤집힌 이름이라 멈추는 쪽이 안전하다 — 메시지가 고칠 방법을 알려 준다. 이 저장소 작업 PC 의 로컬 `.env` 도 해당돼, 로컬에서 `.env` 를 읽는 subprocess 테스트 5건은 `.env` 를 고칠 때까지 실패한다(`.env` 없는 클론·CI 는 통과, run-log Round 2) | 2026-10-12 | 영구 — 설정 이름을 다시 바꾸면 같은 방식으로 |
| R-005 | 실기동 스모크는 엔진을 SQLite 로 바꿔 끼운 런처로 돌렸다(앱 엔진은 MySQL URL 로만 만들어진다) | LOW | 저장소 규칙상 로컬 MySQL·docker 를 쓰지 않는다. MySQL 경로는 `mysql` 마커 테스트(실제 `python -m scripts.create_superuser` subprocess)가 CI 에서 확인한다 | 2026-10-12 | CI 의 MySQL job 이 실패하면 |

> R-002 상태(2026-10-19): **해소** — security-ops-hardening F-003. 로그인 폼에 synchronizer token(관리 세션의 `csrf_token`, 폼 hidden 필드)을 싣고 `login` 이 레이트 리밋보다 먼저 `hmac.compare_digest` 로 대조한다(불일치 403). 로그인 이후 sqladmin 폼의 토큰 부재는 security-ops-hardening R-001 로 이어진다.
> R-001 상태(2026-10-19): 그대로 — 관리 세션의 Redis 이전은 사용자 결정 대기(security-ops-hardening ADR-006).

> R-001 상태(2026-10-19, 2차): **해소** — admin-session-hardening F-001·F-002·F-005. 관리 세션이 Redis 서버 세션이 됐다(쿠키에는 무작위 세션 ID 만, 키 `admin:sess:{HMAC}`). 로그아웃은 서버 키를 지워 복사한 쿠키도 즉시 무효이고, 강등·비활성화·삭제(API·관리 화면)는 그 사용자의 모든 관리 세션을 지운다. 미사용 30분·절대 8시간 만료(`ADMIN_SESSION_*`).
