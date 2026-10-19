# Design Baseline — admin-login (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다.
> 모든 추가 작업은 여기 기록된 Active 요구사항과 불가침 제약을 위반하지 않아야 한다. append-only —
> 항목은 지우지 않고 상태(Active/Superseded)만 바꾼다.
>
> **ID 범위:** `REQ-0xx`·`ADR-0xx`·`C-x`·`F-0xx`·`R-0xx` 는 **이 그룹 안에서만** 번호를 매긴다. 그룹 밖에서 인용할 때는
> `admin-login ADR-0xx` 처럼 그룹 이름을 붙인다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-12 · 변경 이력: (없음)

## 1. 목적 / 배경

`service-hardening` 그룹이 API 에 인증·인가를 붙였지만 SQLAdmin(`/admin`)은 그 밖에 남아 **인증 없이** 열렸다
(그 그룹 ADR-019·C-9·R-001, `orm-raw-repository` C-8·ADR-045 ③·R-004). 이 그룹은 관리 화면에 슈퍼유저 로그인을 붙이고,
관리 화면을 완전히 끄는 설정을 두며, 배포 전에 할 일을 운영자가 보는 모든 문서에 일관되게 적는다.

선행 그룹의 Active 불가침 제약은 이 그룹에도 적용된다(§4 C-4). 단 `service-hardening` C-9("SQLAdmin 정책은 바꾸지 않는다")와
`orm-raw-repository` C-8 의 "인증 백엔드 없음" 부분은 이 요청으로 대체된다(ADR-004).

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-12 | "배포 전에 해야 할 일 에 대해 관련한 모든 문서와 주석에 업데이트를 수행해줘. bootstrap 기반으로 로그인 화면을 만들고 scripts/create_superuser.py로 생성자를 임의로 만들어 /admin에 로그인을 붙여 테스트를 수행해줘. 이후 로그인 페이지 구현 및 연동은 그대로 유지해줘." 이전 원칙(같은 목적 = 한 클래스, 조합·인증은 주입, 모든 단계에 단위 테스트) 유지 | 아래 REQ-001-A~D | Active | ADR-001~004·007·008, C-1~C-5 |
| REQ-001-A | 2026-10-12 | (배포 전 할 일) | `TRUSTED_PROXY_HOPS`·KST→UTC 리비전 가정과 백업·첫 관리자 `create_superuser`·`/admin` 슈퍼유저 로그인(`SESSION_SECRET_KEY`)을 README 체크리스트(각 한 항목)·`.env.example`·config 주석·가이드·리비전 docstring·`ClientIPResolver`·`create_superuser` docstring·조립 지점 docstring 에 일관되게 | Active | ADR-008, ledger F-004 |
| REQ-001-B | 2026-10-12 | (/admin 로그인) | `AdminAuthBackend` 한 클래스, 활성 슈퍼유저만, 레이트 리밋(키 분리)·429 화면, 세션 고정 방지, 매 요청 DB 확인, 쿠키 속성, `ADMIN_ALLOW_UNAUTHENTICATED` 제거 | Active | ADR-001·002·004, ledger F-001 |
| REQ-001-C | 2026-10-12 | (Bootstrap 화면) | `sqladmin/login.html` 덮어쓰기, Bootstrap 5.3.x CSS + SRI, 접근성 레이블, 이스케이프, JS 없음. 화면과 연동은 **유지 대상** | Active | ADR-003, C-2 |
| REQ-001-D | 2026-10-12 | (Celery include) | include 모듈을 실제로 import 해 태스크 등록을 보는 테스트 1건 | Active | ADR-007, ledger F-002 |
| REQ-002 | 2026-10-12 | "이 작업과 관련하여 차후 설계 및 동작을 이해할 수 있게 별도의 admin 인증 가이드 문서를 만들어줘. 세션과 관련한 인증이 admin에만 적용되고 다른 api 인증 및 별도 작업에는 사용하지 않는것인지 확인하고 맞다면 이에 관련한 정보와 워크플로우 흐름도 등 상세한 설명을 정리해줘. 필요한 모든 도식화를 구현해 설명에 추가해줘. admin 페이지 자체를 사용하지 않는 설정이 존재해야 한다. 이 설정이 true이면, admin 페이지에 대한 링크 자체가 존재하지 않아야 한다. 이는 보안을 위해서 존재해야 한다." 사용자 결정: `ADMIN` → `ADMIN_DISABLED` 교체 | `ADMIN_DISABLED`(true=끔, 잔존 `ADMIN` 은 기동 거부), 끈 상태의 4가지 보장, 세션 범위 확인 테스트, `docs/guides/admin-auth-guide.html`(도식 포함) | Active | ADR-005·006·008, ledger F-003 |
| REQ-003 | 2026-10-12 | "관련하여 모든 문서도 내용을 업데이트 하여 반영해줘" | 이 그룹의 모든 변경을 README·`.env.example`·`docs/guides/*`·CRP·docstring 에 반영하고 낡은 서술을 grep 으로 확인 | Active | ADR-008, run-log Round 2 |
| REQ-004 | 2026-10-12 | (감독자 확인 지시) 다른 작업에서 sqladmin 0.32 `column_filters` 에 모델 컬럼을 그대로 넘겨 로그인 후 목록 화면이 500 이 된 결함이 나왔다 — 이 저장소에서도 확인하고 같으면 `sqladmin.filters` 로 고칠 것 | 모든 ModelView 의 목록(필터 포함)·상세 1건이 로그인 상태로 200 인 테스트, 실기동 스모크에서도 목록 확인 | Active | ADR-009, ledger F-005 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-12 | **로그인 백엔드는 auth 기능의 한 클래스** `AdminAuthBackend(sqladmin.authentication.AuthenticationBackend)` — `app/features/auth/admin_backend.py`. 생성자 주입: 서명 키, `https_only`, 세션 팩토리(`background_db_session`), `auth_service_factory(request, session) -> AuthService`, `rate_limiter_factory(request) -> RateLimiter`, `ClientIPResolver`. 조립은 `app/features/admin.py` 의 `build_admin_auth_backend(app, session_factory=...)` 가 **기존 provider**(`get_password_hasher`·`get_token_service`·`get_refresh_token_store`·`get_rate_limiter`)로 한다. 자격 확인은 API 로그인의 `AuthService.authenticate` 를 그대로 쓰고(재해시면 커밋), 식별자는 `username`. 레이트 리밋은 같은 한도 설정(`AUTH_LOGIN_*`)·키 접두사 `admin:rl:login:`. 성공 시 IP+사용자명 카운터 초기화, `session.clear()` 후 `user_id` 만. `authenticate` 는 매 요청 `UserRepository.get_by_id` 로 활성·슈퍼유저 확인, 아니면 세션을 비운다. 실패 사유 미구분(400), 한도 초과 429 + `Retry-After` 로 로그인 화면 재표시, 로그는 사용자명(64자)·IP 만. | 계층 규칙(`service-hardening` C-2): 사용자 조회가 필요해 core 에 둘 수 없고, auth→user 는 문서화된 허용 간선이다. 명세는 `PasswordHasher`·`RateLimiter` 를 직접 주입하라고 했으나 **명세 대비 차이**: Redis 는 lifespan 이 연 `app.state.redis` 라 생성 시점(모듈 import)에 없다 — 그래서 Redis 를 요구하는 협력 객체는 요청 시점에 기존 provider 로 만드는 팩토리를 주입한다. 또 SQLAdmin 은 하위 Starlette 앱이라 `request.app` 이 바깥 앱이 아니어서 `get_redis(request)` 로는 닿지 않는다 — 조립 함수가 바깥 앱을 클로저로 잡는다(`_app_redis`). 검증 코드를 복제하지 않으려 `AuthService` 를 통째로 쓰므로 해시기는 그 팩토리 안에서 주입된다. sqladmin 기본 실패 문구("Invalid credentials.")는 영어라 백엔드가 같은 템플릿으로 400 을 직접 그린다. | Accepted | — |
| ADR-002 | 2026-10-12 | 세션은 starlette `SessionMiddleware`(SQLAdmin 이 백엔드의 `middlewares` 로 하위 앱에만 붙인다). 쿠키 `admin_session`, `path=/admin`, `SameSite=Strict`, HttpOnly, `Max-Age` 8시간, `https_only` 는 `ENV ∈ {staging, production}`. 서명 키는 기존 `SESSION_SECRET_KEY`. 의존성 **`itsdangerous` 추가**(`uv add itsdangerous`, 2.2.0). | starlette 의 `SessionMiddleware` 가 itsdangerous `TimestampSigner` 로 쿠키를 서명하는데 starlette 는 itsdangerous 를 선택 의존성으로 둔다 — 설치돼 있지 않아 import 단계에서 실패한다. 서버 세션 저장소를 따로 두지 않는 가장 작은 방법이다. 쿠키 이름을 기존 `SESSION_COOKIE_NAME` 과 다르게 해 접속 로그의 `session_id` 기록과 섞이지 않게 한다. | Accepted | — |
| ADR-003 | 2026-10-12 | 로그인 화면은 `app/templates/admin/sqladmin/login.html`(독립 HTML, base 미확장) — `create_admin_interface()` 가 `templates_dir` 로 주입한다. sqladmin 0.32 의 로더는 `ChoiceLoader([FileSystemLoader(templates_dir), PrefixLoader(sqladmin_original), PackageLoader("sqladmin", "templates")])` 라 같은 이름이면 우리 파일이 먼저다(`sqladmin/application.py` `init_templating_engine`). Bootstrap **5.3.8** CSS 를 jsDelivr 에서 `integrity="sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB"`·`crossorigin="anonymous"` 로 로드(해시는 실제 파일을 내려받아 `openssl dgst -sha384` 로 계산). JS 없음. 백엔드는 생성된 `Admin` 의 템플릿 환경을 받는다(`backend.templates = admin.templates`). | 5.3.x 의 최신 패치. SRI 가 CDN 변조를 막는다. 템플릿 경로는 작업 디렉터리와 무관하게 절대 경로로 준다. `Admin` 이 백엔드를 생성 인자로 받으므로 백엔드가 템플릿을 생성자로 받을 수 없어 생성 직후 연결한다. | Accepted | — |
| ADR-004 | 2026-10-12 | 설정 `ADMIN_ALLOW_UNAUTHENTICATED`·배포 안전 검사의 "확인 없는 ADMIN=true" 위반·기동 WARNING 을 **제거**한다. 남은 `.env` 줄은 `extra="ignore"` 로 무시된다(기동 유지). | 관리 화면에 로그인이 붙어 "인증 없는 화면을 알고 켰다" 는 확인이 의미를 잃었다. `orm-raw-repository` ADR-045 ③·C-8(인증 백엔드 없음 부분), `service-hardening` ADR-019·C-9·R-001 을 대체한다. | Accepted | orm-raw-repository ADR-045 ③, service-hardening ADR-019 |
| ADR-005 | 2026-10-12 | `ADMIN`(true=켬)을 **`ADMIN_DISABLED`(기본 false, true=끔)로 교체**한다. 예전 `ADMIN` 이 환경 변수나 `.env` 에 남아 있으면(대소문자 무시) `config.validate_no_legacy_admin()` 이 import 시점에 `RuntimeError` 로 멈춘다(ENV=test 제외 — `validate_env_source` 와 같은 기준, 감지는 config.py 안). true 면: `/admin` 이하 404(마운트 없음, sqladmin·백엔드·세션 미들웨어 미생성), 앱 응답(OpenAPI·`/docs`·공개 GET·오류 본문·헤더)에 `/admin` 없음, 기동 로그는 "관리 화면 비활성화 (ADMIN_DISABLED=true)". 이를 위해 `API_DESCRIPTION`(OpenAPI `info.description`)에서 관리 화면 행을 뺀다. | 사용자 결정. 뜻이 뒤집힌 이름을 조용히 무시하면 `ADMIN=false` 로 꺼 둔 배포가 켜진 채 뜬다. 쓰지 않는 관리 화면은 로그인 화면조차 공격 표면이므로 흔적 없이 없앤다. | Accepted | — |
| ADR-006 | 2026-10-12 | **세션 인증은 `/admin` 전용**임을 확인하고 테스트로 고정한다 — 메인 앱 `user_middleware` 에 `SessionMiddleware` 없음, 하위 앱에만 있음(쿠키 이름·path), 유효한 `admin_session` 쿠키만으로 API 보호 경로는 401, `/admin` 밖 응답은 `admin_session` 을 설정하지 않음. `SESSION_SECRET_KEY` 소비처는 관리 세션 서명과 설정 검사(예시 값·길이, `.env` 부재 시 필수 목록)뿐이다. | 감독자 사전 확인과 코드 대조(`request.session` 사용처는 `admin_backend.py` 하나, `SESSION_COOKIE_NAME` 은 접속 로그 기록용)가 일치했다. 두 인증 체계를 섞으면 API 에 CSRF 방어가 필요해지고 폐기·수명이 엇갈린다. | Accepted | — |
| ADR-007 | 2026-10-12 | `tests/core/test_celery_app.py::test_every_include_module_imports_and_registers_its_tasks` — `celery_app.conf.include` 의 모든 모듈을 `importlib.import_module` 하고, 각 모듈이 태스크를 하나 이상 등록했는지 본다. | 탐색은 `find_spec` 으로 존재만 확인하고 import 하지 않는다(`service-hardening` ADR-024 ③). `tasks.py` 의 import 오류가 워커 기동 때에야 드러났다. 기존 `test_aggregate_task_registered_through_discovery` 는 home 태스크 하나만 본다 — 새 기능의 `tasks.py` 도 자동으로 검사 대상이 된다. | Accepted | — |
| ADR-008 | 2026-10-12 | 문서: README 운영 배포 체크리스트에 배포 전 할 일 4개(A `TRUSTED_PROXY_HOPS` · B KST→UTC 리비전 가정·`_LEGACY_OFFSET`·백업 · C `create_superuser` · D `/admin` 로그인·`SESSION_SECRET_KEY`·`ADMIN_DISABLED`)를 각 한 항목으로. 관리 화면 인증은 `docs/guides/admin-auth-guide.html` 이 원본(기존 HTML 가이드와 같은 스타일·Mermaid 11.12.0 CDN·원문 `<details>` 대체), README 문서 표·ARCHITECTURE §12 에서 링크. | 운영자가 보는 곳마다 같은 문구여야 한다. 기존 가이드의 도식 방식을 따라 오프라인에서도 원문으로 읽힌다. | Accepted | — |
| ADR-009 | 2026-10-12 | 기능 `admin.py` 의 `column_filters` 는 `sqladmin.filters` 객체로 둔다 — 불리언은 `BooleanFilter`, 문자열·숫자는 `OperationColumnFilter`. 생성 시각(`UTCDateTime`) 필터는 뺀다(reports 는 필터 없음). | sqladmin 0.32 의 `ModelView.list` 는 `filter_.parameter_name` 을 읽는다 — 컬럼을 넣으면 `AttributeError` 로 목록 화면이 500 이었다(재현 확인). `OperationColumnFilter` 는 `isinstance(type, DateTime)` 으로 날짜를 판정하는데 `UTCDateTime` 은 `TypeDecorator` 라 문자열 그대로 바인딩되고 `process_bind_param` 이 실패한다(변이로 500 확인). 시각은 목록 정렬로 본다. 필터 서브클래스를 새로 만들지 않는다. | Superseded(생성 시각 필터 부분 — security-ops-hardening ADR-005 `LocalDateFilter`, 2026-10-19) | — |

## 4. 불가침 제약

- **C-1**: 관리 세션은 SQLAdmin 하위 앱 전용이다 — 메인 앱에 세션 미들웨어를 두지 않고, API 인증에 세션 쿠키를 쓰지 않는다(ADR-006).
- **C-2**: 로그인 화면(`app/templates/admin/sqladmin/login.html`)과 연동(`AdminAuthBackend`·`create_admin_interface` 주입)은 유지한다 — 사용자 요청 "이후 로그인 페이지 구현 및 연동은 그대로 유지". 바꿀 때는 form action·필드 이름·이스케이프·SRI 를 지킨다.
- **C-3**: `ADMIN_DISABLED=true` 는 흔적을 남기지 않는다 — 마운트·import·응답·기동 로그(ADR-005).
- **C-4**: `service-hardening` 의 Active 불가침 제약 C-1~C-8·C-10 을 계승한다(C-9 는 ADR-004 로 대체).
- **C-5**: 비밀번호·해시·세션 쿠키 값을 로그·오류 응답에 싣지 않는다.

## 5. 변경 이력

- v0.1 (2026-10-12): 최초 작성. REQ-001(A~D), ADR-001~004·007·008, C-1~C-5.
- v0.2 (2026-10-12): 추가 요청 REQ-002·REQ-003, ADR-005·006 추가, ADR-008 에 안내서를 더한다.
- v0.3 (2026-10-12): 감독자 확인 지시 REQ-004, ADR-009(필터 객체) 추가.
