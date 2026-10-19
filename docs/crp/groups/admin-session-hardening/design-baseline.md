# Design Baseline — admin-session-hardening (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태(Active/Superseded)만 바꾼다.
>
> **ID 범위:** `REQ-0xx`·`ADR-0xx`·`C-x`·`F-0xx`·`R-0xx` 는 **이 그룹 안에서만** 번호를 매긴다. 그룹 밖에서 인용할 때는
> `admin-session-hardening ADR-0xx` 처럼 그룹 이름을 붙인다(코드 주석의 `admin-session-hardening ADR-0xx` 는 이 그룹이다).

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-19 · 변경 이력: (없음)

## 1. 목적 / 배경

이전 그룹이 남긴 관리 화면의 잔여 위험을 닫는다. ① 관리 세션이 서명 쿠키(starlette `SessionMiddleware`, 내용 전체가 쿠키)라
서버에서 폐기할 수 없었다 — 로그아웃 전에 복사된 쿠키는 8시간 유효(admin-login R-001). ② 로그인 **이후** sqladmin 이 그리는
생성·수정·삭제 요청과 GET 로그아웃에 CSRF 토큰이 없었다(security-ops-hardening R-001). ③ 날짜 필터가 한 번에 한쪽 경계만
걸었다(security-ops-hardening R-004). ④ 405 `Allow` 불완전(log-redaction-fixes R-002)은 사용자가 현행 유지로 결정했다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-19 | "관리 화면에 로그인한 뒤 쓰는 생성·수정·삭제 폼과, GET 방식 로그아웃 링크의 CSRF 토큰 / 관리 세션을 Redis로 옮기는 작업 / 필터 하나로 시작일~종료일 범위를 한 번에 지정하는 기능 — 이 작업들을 진행해줘. redis는 방법 2로 진행해줘. 405 문제는 현행 유지한다." 원칙 유지: 같은 목적은 하나의 모듈 클래스, 조합·데이터 전달·인증·자동 작업은 주입, 모든 단계 단위 테스트(fail-on-revert) | 아래 REQ-001-A~C, REQ-002 | Active | ADR-001~006, C-1~C-5 |
| REQ-001-A | 2026-10-19 | (관리 세션 Redis — 방법 2: 서버 세션) | 쿠키에는 무작위 세션 ID 만, 내용은 Redis. 절대 8시간 + 미사용 30분(설정), 로그인 시 세션 ID 회전, 로그아웃·강등·비활성화·삭제(·비밀번호 변경) 시 서버에서 즉시 폐기, Redis 장애 fail-closed | Active | ADR-001·ADR-002, ledger F-001·F-002 |
| REQ-001-B | 2026-10-19 | (로그인 이후 CSRF) | `/admin` 의 POST·PUT·PATCH·DELETE 전부와 로그아웃에 synchronizer token. 로그아웃은 POST + 토큰. 클라이언트는 덮어쓴 템플릿의 meta·스크립트 | Active | ADR-003·ADR-004, ledger F-003 |
| REQ-001-C | 2026-10-19 | (기간 필터) | `LocalDateFilter` 한 필터에서 시작일~종료일(양 끝 포함, 한쪽만이면 열린 구간, 역순·형식 오류는 미적용 + WARNING) | Active | ADR-005, ledger F-004 |
| REQ-003 | 2026-10-19 | (감독자 추가 범위) "관리 화면(UserAdmin)에서 사용자를 직접 수정(is_active=False·is_superuser 해제·비밀번호 변경)하거나 삭제했을 때도 그 사용자의 관리 세션을 즉시 전부 폐기하라. ... 서비스 계층과 같은 폐기 함수(revoke_user)를 부른다 — 폐기 로직을 중복 구현하지 말 것. 조건: 변경 전후를 비교해 비활성화·강등·비밀번호 변경·삭제일 때만(이름 등 일반 수정은 폐기 안 함). 자기 자신을 강등하면 현재 세션도 끊긴다 — 그대로 둔다(문서화). Redis 오류는 fail-closed 정책과 같게." | 관리 화면 수정·삭제 훅이 변경 전(모델)과 저장할 값(data)을 비교해 비활성화·슈퍼유저 해제·비밀번호 해시 변경·삭제일 때만 `AdminSessionStore.revoke_user`. 일반 수정은 유지. 자기 강등은 현재 세션도 끊김. 폐기 실패 시 변경을 저장하지 않는다 | Active | ADR-007, ledger F-005 |
| REQ-002 | 2026-10-19 | "405 문제는 현행 유지한다." (사용자 결정) | 같은 경로를 메서드별 라우트로 나눈 곳의 405 `Allow` 불완전을 고치지 않는다 | Active | ADR-006 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-19 | 관리 세션은 Redis 서버 세션이다. `app/core/security/admin_session.py` 에 저장소 클래스 `AdminSessionStore`(저장·조회·삭제·사용자 단위 폐기)와 ASGI 미들웨어 `RedisSessionMiddleware` 를 둔다. 쿠키 `admin_session` = `secrets.token_urlsafe(32)`. 키 `admin:sess:{HMAC-SHA256(SESSION_SECRET_KEY, sid)}` → JSON `{"data", "user_id", "created_at"}`, 인덱스 `admin:user_sessions:{user_id}`(SET, TTL=절대 만료). 만료: 절대 `ADMIN_SESSION_MAX_AGE_SECONDS`(기본 28800, 연장 불가 — `load` 가 `created_at` 으로 확인) + 미사용 `ADMIN_SESSION_IDLE_SECONDS`(기본 1800, 요청마다 `TTL=min(idle, 남은 절대)`), 둘 다 `ge=60`, idle ≤ max(모델 검증). 기존 세션 저장은 `SET XX`, 새 세션은 `SET NX`. 미들웨어는 `scope["session"]` 에 dict 를 넣어 `request.session` 을 그대로 쓰고, 응답 시작(`http.response.start`) 때 저장·Set-Cookie 를 한다: 빈 세션이면 키 삭제 + 쿠키 삭제, 쿠키의 sid 가 Redis 에 없으면 빈 세션 + 쿠키 삭제, 새 세션만 `Max-Age`=절대 만료로 쿠키를 내린다. 세션 고정 방지는 `rotate_session(request)`(scope 플래그) — 미들웨어가 새 sid 발급·이전 키 삭제. Redis 장애(`RedisError`·`ServiceUnavailableException`·`OSError`)는 응답 전이면 503(fail-closed). Redis 는 `_app_redis(app)` 로 **요청마다** 받아 저장소를 만든다(`new_admin_session_store`). `AdminAuthBackend` 는 부모 생성자를 부르지 않고 `middlewares` 를 이 미들웨어로 바꿔 끼운다. 의존성 `itsdangerous` 제거(다른 소비처 없음 — `grep`, `uv remove`). | 방법 2(서버 세션)를 사용자가 골랐다. 저장소를 미들웨어·폐기 훅·테스트가 함께 쓰므로 미들웨어와 분리했다(같은 목적 = 한 클래스). HMAC 키라 Redis 키 목록이 새도 쿠키를 만들 수 없다. `SET XX` 가 없으면 요청 처리 중 폐기된 세션을 그 응답이 다시 써 되살린다(변이로 확인). 회전을 scope 플래그로 알리는 것이 백엔드에 저장소를 주입해 직접 회전하는 것보다 단순하다(쿠키 발급 주체가 하나). 미들웨어는 앱 조립(import) 시점에 생기지만 Redis 는 lifespan 뒤에야 있으므로 팩토리로 받는다. | Accepted | admin-login ADR-002(세션 방식) |
| ADR-002 | 2026-10-19 | 즉시 폐기: 비활성화·슈퍼유저 강등·삭제 시 `AdminSessionStore.revoke_user(user_id)`. API 경로는 `UserService` 가 refresh `revoke_user` 와 같은 자리에서 주입받은 저장소를 부른다(provider `get_admin_session_store` — `ADMIN_DISABLED=true` 면 `None`, 생성자 인자 `admin_sessions: AdminSessionStore \| None`). 관리 화면 경로는 `UserAdmin.after_model_change`(활성·슈퍼유저가 아니게 된 경우)·`after_model_delete` 가 이 요청의 저장소(`request_session_store(request)` — 미들웨어가 scope 에 둔다)로 부른다. 비밀번호 변경 경로는 없다(API `UserUpdate` 에 비밀번호 없음, 관리 폼은 `hashed_password` 제외) — 생기면 같은 자리에서 함께 폐기. `authenticate` 의 매 요청 DB 확인은 유지(이중 방어). | 명세 "이미 refresh 토큰을 revoke_user 하는 지점이 있으면 같은 지점에서 store 를 주입받아 함께 호출". 관리 화면에서도 사용자를 비활성화·강등·삭제할 수 있는데(sqladmin 폼에 `is_active`·`is_superuser`), 그 경로는 `UserService` 를 거치지 않는다 — 훅이 없으면 재활성화 시 복사된 쿠키가 미사용 만료 전까지 되살아난다. user 기능은 auth 기능을 import 할 수 없으므로(service-hardening C-2) 저장소는 core 에 둔다. | Accepted | — |
| ADR-003 | 2026-10-19 | CSRF 검사는 관리 하위 앱의 `AdminCsrfMiddleware` 하나(세션 미들웨어 안쪽). 대상: POST·PUT·PATCH·DELETE 전부 — 로그인·로그아웃 포함(로그인 폼 검사를 `AdminAuthBackend.login` 에서 이 미들웨어로 **옮겨** 중복 없이 한 곳). 토큰: 헤더 `X-CSRF-Token` 우선, 없고 본문이 폼(`x-www-form-urlencoded`·`multipart/form-data`)이면 본문을 끝까지 버퍼링(상한 10 MiB, 넘으면 413)해 Starlette 폼 파서로 `csrf_token` 을 읽고, 같은 바이트를 다운스트림 `receive` 로 한 번 재생한 뒤 원래 `receive` 로 넘긴다. 세션에 토큰이 없으면 본문을 읽지 않고 거부. 비교는 `hmac.compare_digest`(bytes). 실패 응답은 주입한 `reject`(= `AdminAuthBackend.csrf_rejected`)가 그린다 — 로그인 POST 는 로그인 화면(403, 새 토큰), 그 밖은 `sqladmin/error.html`(403). 토큰 생성 `csrf_token(request)` 도 같은 모듈로 옮겨 템플릿 전역으로 연결한다. | 헤더로만 통일하면 생성·수정(브라우저 네이티브 폼 제출)에 헤더를 붙일 수 없어 JS 가 폼 제출을 fetch 로 바꿔야 한다 — sqladmin 의 응답(302·400 재렌더)을 그대로 쓰려면 네이티브 제출이 낫다. 본문 버퍼링 + 재생은 Starlette 에서 다운스트림이 본문을 다시 읽게 하는 표준 방법이고, 미들웨어가 엔드포인트보다 먼저라 위조 로그인 POST 가 레이트 리밋에 닿지 않는 security-ops-hardening C-3 이 그대로 지켜진다. 익명 요청이 큰 본문을 버퍼링시키지 못하게 세션 토큰 확인을 먼저 한다. | Accepted | security-ops-hardening ADR-004(검사 위치만 — 토큰·화면은 같다) |
| ADR-004 | 2026-10-19 | 클라이언트: `app/templates/admin/sqladmin/base.html` 이 원본을 복사하지 않고 `sqladmin_original/base.html`(sqladmin 0.32 의 `PrefixLoader`)을 확장해 `head_meta` 에 `<meta name="csrf-token">`, `tail` 에 인라인 스크립트(① `method=post` 폼 submit 캡처 → hidden `csrf_token`, ② `XMLHttpRequest.prototype.open/send`·`window.fetch` 를 감싸 같은 출처의 비안전 메서드에 `X-CSRF-Token`, ③ 로그아웃 링크(`a[href]` 가 `url_for('admin:logout')`) 클릭 → 토큰 실은 POST 폼 제출)를 더한다. 로그아웃: sqladmin 의 `Route("/logout", methods=["GET"])` 을 `create_admin_interface` 가 같은 엔드포인트의 POST 전용 라우트로 교체(`_logout_post_only`, 라우트 이름으로 찾고 없으면 기동 실패) — GET 은 405. 드리프트 테스트: 덮어쓴 템플릿은 두 블록만·`super()` 2회, 원본 base 의 블록·layout 의 로그아웃 링크·`extends "sqladmin/base.html"`·`PrefixLoader`·원본 로그아웃 라우트가 GET 전용인지·`main.js` 의 DELETE·fetch·action 경로. sqladmin `@action`(GET 상태 변경)은 등록하지 않는다(테스트). | sqladmin 0.32 소스·템플릿·`main.js` 조사 결과(run-log 표): 상태 변경은 create/edit 네이티브 POST 폼, 삭제·일괄 삭제 `$.ajax` DELETE, import `fetch` POST, 사용자 정의 action GET(`window.location`), 로그아웃 GET 링크. 확장 방식이면 원본이 바뀌어도 덮어쓴 블록 밖은 따라간다. 로그아웃 라우트 교체가 템플릿 링크를 폼으로 바꾸는 것(layout 전체 복사 필요)보다 작고, GET 을 서버에서 막는 것이 확실하다. | Accepted | — |
| ADR-005 | 2026-10-19 | `LocalDateFilter` 에 연산 `between`(기간(양 끝 포함)). 값 `YYYY-MM-DD~YYYY-MM-DD` — `date_range()` 가 [시작일 0시, 종료일 다음날 0시) 를 UTC aware 로 돌려준다. 한쪽만 주면 열린 구간(`2026-10-01~`·`~2026-10-19`). 구분자 없음·양쪽 빔·형식 오류·시작일 > 종료일·날짜 범위 넘침은 필터 미적용 + WARNING. 필터 템플릿은 기존 단일 날짜 폼(연산 select 에서 `between` 제외) 아래에 두 번째 폼(hidden `{name}_op=between`·hidden `{name}`, 이름 없는 날짜 입력 둘, `onsubmit` 이 `start~end` 로 합침, 둘 다 비면 제출 안 함)을 둔다. 빠른 선택은 그대로. | sqladmin 0.32 는 연산 필터에 값 하나(`request.query_params.get(name)`)만 넘긴다(`ModelView.get_model_objects` 소스) — 값 형식으로 두 날짜를 싣는 것이 프로토콜 안에서 가장 작다. 종료일을 "다음날 0시 미만" 으로 두면 23:59:59.999999 와 DST(23·25시간 날)를 함께 맞는다. | Accepted | security-ops-hardening ADR-005 의 연산 3종(확장) |
| ADR-006 | 2026-10-19 | **사용자 결정:** 405 `Allow` 헤더 불완전(같은 경로를 메서드별 라우트로 나눈 곳은 Starlette 가 처음 부분 일치한 라우트의 메서드만 싣는다)을 **현행 유지**한다. log-redaction-fixes R-002 에 "사용자 결정으로 수용(2026-10-19)" 을 덧붙인다. 이번 그룹의 로그아웃 POST 전용 교체로 `GET /admin/logout` 의 405 도 같은 Starlette 동작이다(`Allow: POST`). | 기능·보안 영향이 없고(헤더 전달 자체는 정상, 메서드 거부는 정확), 고치려면 405 핸들러가 FastAPI 0.141 내부(`_IncludedRouter`)를 순회해야 한다. | Accepted | — |
| ADR-007 | 2026-10-19 | 관리 화면 폐기 훅은 sqladmin 0.32 의 **`on_model_change`·`on_model_delete`**(커밋 전)에 둔다(ADR-002 의 `after_model_change`·`after_model_delete` 를 대체). `on_model_change` 는 수정(`is_created=False`)이고 `revokes_admin_sessions(user, data)` — `user.is_active and data["is_active"] is False` 또는 `user.is_superuser and data["is_superuser"] is False` 또는 `data` 에 `hashed_password` 가 있고 기존 해시와 다름 — 일 때만 `request_session_store(request).revoke_user(user.id)`. `on_model_delete` 는 항상 폐기. 이름·이메일 등 일반 수정은 폐기하지 않는다. 자기 자신을 강등·비활성화하면 현재 세션도 지워져 다음 요청은 로그인 화면이다(의도, 안내서에 문서화). | sqladmin 소스(`_queries.py` `_update_async`·`_delete_async`): `on_model_change(data, obj)` 는 값이 적용되기 **전**의 객체와 저장할 `data` 를 함께 받아 "변경 전후 비교" 를 추가 상태 없이 할 수 있고, 커밋 전이라 Redis 오류가 나면 예외가 커밋을 막는다 — sqladmin 이 예외를 잡아 폼을 오류로 다시 그리고 변경은 저장되지 않는다(fail-closed: 세션은 살고 비활성화만 저장되는 상태가 없다). `after_*` 는 커밋 뒤라 폐기 실패가 "저장됨 + 세션 생존" 을 남긴다(변이로 확인). API 경로의 `UserService` 도 커밋 전에 폐기한다. 폐기 자체는 같은 `AdminSessionStore.revoke_user` 로 중복 구현하지 않는다. 관리 폼은 비밀번호를 다루지 않지만(`hashed_password` 제외) 해시가 data 에 실리는 경로가 생기면 같은 비교가 잡는다. | Accepted | ADR-002 의 관리 화면 훅 부분 |

## 4. 불가침 제약

- **C-1**: 관리 세션 쿠키에는 세션 ID 외의 값을 싣지 않는다. 세션 내용은 Redis 에만 있다(`test_cookie_carries_only_a_random_session_id`).
- **C-2**: 관리 세션 저장소(Redis) 장애에서 관리 화면은 요청을 통과시키지 않는다(`test_redis_outage_is_503_not_a_pass`).
- **C-3**: `/admin` 의 비안전 메서드 요청은 모두 `AdminCsrfMiddleware` 를 거친다. 상태를 바꾸는 GET(로그아웃·sqladmin `@action`)을 두지 않는다(`test_get_logout_does_not_log_out`, `test_no_view_registers_a_custom_get_action`).
- **C-4**: 사용자를 비활성화·강등·삭제(관리 화면은 비밀번호 해시 변경 포함)하는 코드 경로는 커밋 **전에** 관리 세션 폐기를 부른다(`test_user_service_revokes_every_admin_session_of_that_user`, `test_admin_ui_edit_revokes_only_on_deactivation_or_demotion`, `test_admin_ui_revocation_failure_keeps_the_user_unchanged`).
- **C-5**: 선행 그룹의 Active 불가침 제약(`service-hardening` C-1~C-8·C-10, `admin-login` C-1~C-5, `log-redaction-fixes` C-1~C-5, `access-policy` C-1~C-3, `security-ops-hardening` C-1~C-4)을 계승한다.

## 5. 변경 이력

- v0.1 (2026-10-19): 최초 작성. REQ-001(A~C)·REQ-002, ADR-001~006, C-1~C-5.
- v0.2 (2026-10-19): 감독자 추가 범위 REQ-003 · ADR-007(관리 화면 폐기 훅을 커밋 전 훅 + 변경 전후 비교로).
