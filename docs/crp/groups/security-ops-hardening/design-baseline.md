# Design Baseline — security-ops-hardening (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태(Active/Superseded)만 바꾼다.
>
> **ID 범위:** `REQ-0xx`·`ADR-0xx`·`C-x`·`F-0xx`·`R-0xx` 는 **이 그룹 안에서만** 번호를 매긴다. 그룹 밖에서 인용할 때는
> `security-ops-hardening ADR-0xx` 처럼 그룹 이름을 붙인다(코드 주석의 `security-ops-hardening ADR-0xx` 는 이 그룹이다).

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-19 · 변경 이력: (없음)

## 1. 목적 / 배경

검수 문서와 이전 그룹의 잔여 위험에 남아 있던 보안·운영 항목을 닫는다. ① DB 드라이버 예외 문자열의 바인드 값(이 저장소는
`hide_parameters=True` 가 이미 있었다 — 빠진 엔진이 없는지 확인하고 회귀를 고정), ② 접속 로그에 보존 기간이 없어 원문 그대로
무기한 쌓이던 것(log-redaction R-001), ③ 관리 로그인 폼에 CSRF 토큰이 없던 것(admin-login R-002), ④ 관리 목록에서 생성 시각
필터를 뺐던 것(admin-login ADR-009 — sqladmin 연산 필터가 `UTCDateTime` 을 날짜형으로 보지 못해 500).

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-19 | "보안결함 진행해줘. 접속 로그 보존 기간은 기본 1년으로 설정하고 이는 설정값으로 설정이 가능하도록 만들어줘. .env에 설정이 되도록 해줘. 15분 유지한다. ... 관리 화면 로그인폼에 csrf 토큰 작업을 진행해줘. 관리 화면 목록에 created_at 날자 필터 작업해줘." 원칙 유지: 같은 목적은 하나의 모듈 클래스, 조합·데이터 전달·자동 작업은 주입, 모든 단계 단위 테스트(fail-on-revert) | 아래 REQ-001-A~D | Active | ADR-001~005, C-1~C-4 |
| REQ-001-A | 2026-10-19 | (DB 오류 바인드 값) | 모든 SQLAlchemy 엔진 생성 지점에 `hide_parameters=True`. 이미 있으면 빠진 지점이 없는지 확인하고 회귀 테스트(실제 SQLite 무결성 오류·엔진 계약·로그 파이프라인) | Active | ADR-001, ledger F-001 |
| REQ-001-B | 2026-10-19 | (접속 로그 보존) | `ACCESS_LOG_RETENTION_DAYS`(기본 365, `.env` 설정, 0=삭제 안 함, 음수 거부). 보존 기간이 지난 행을 배치로 지우는 클래스 하나 + Celery beat 하루 1회 | Active | ADR-002·ADR-003, ledger F-002 |
| REQ-001-C | 2026-10-19 | (관리 로그인 CSRF) | `/admin/login` POST 에 synchronizer token — 세션에 저장, 폼 hidden, 레이트 리밋보다 먼저 상수 시간 비교, 불일치 403 | Active | ADR-004, ledger F-003 |
| REQ-001-D | 2026-10-19 | (관리 목록 날짜 필터) | `created_at` 이 있는 모든 ModelView 에 로컬 날짜 필터(같은 날/이후/이전, 잘못된 입력은 500 이 아니라 무시) | Active | ADR-005, ledger F-004 |
| REQ-002 | 2026-10-19 | "15분 유지한다." (사용자 결정) | 액세스 토큰 수명 15분과 "권한 회수는 토큰 만료까지 지연"을 **유지**한다. 관리 세션의 Redis 이전은 이번 범위 밖(사용자 결정 대기) | Active | ADR-006 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-19 | 엔진 생성 지점은 `app/core/db/session.py` 의 셋(writer `engine`·replica `_create_read_engine`·`background_engine`)뿐이고 셋 다 이미 `hide_parameters=True` 다(service-hardening ADR-022) — **코드는 바꾸지 않는다.** 옵션을 상수·헬퍼로 모으는 구조는 없었고 새로 만들지 않는다. 회귀는 `tests/core/test_db_hide_parameters.py` 가 고정한다: (a) **앱 writer 엔진의 설정값을 그대로 받은** SQLite 엔진에서 고유 제약 위반을 일으켜 예외 문자열에 이메일·해시가 없고 `INSERT INTO users` 는 남는지, (b) 앱 엔진 객체(+ 복제 꺼짐에서도 replica 생성 경로) 모두 `hide_parameters is True`, (c) `app/` 에서 `create_async_engine(`·`create_engine(` 이 `session.py` 에만 있고 그 파일의 생성 수와 `hide_parameters=True` 수가 같다, (d) 앱 로그 필터(`SqlNoiseFilter`·`RedactingFilter`)+`TzFormatter` 경로로 `logger.exception` 한 출력에 값이 없다. | 명세 "이미 있으면 빠진 지점이 없는지만 확인". `grep` 결과 앱 코드의 생성 지점은 세 곳이고 테스트 엔진은 대상이 아니다. (a)·(d) 가 앱 설정값을 따라가야 앱에서 옵션을 빼는 변이에 실패한다(fail-on-revert 확인). (c) 는 네 번째 생성 지점이 옵션 없이 생기는 것을 막는다 — 마스킹 필터(`RedactingFilter`)는 이메일·해시 같은 **키 없는 값**을 가리지 못하므로(log-redaction R-003) 엔진 옵션이 1차 방어다. | Accepted | — |
| ADR-002 | 2026-10-19 | 보존 설정은 접속 로그 설정 묶음 `MiddlewareSettings.ACCESS_LOG_RETENTION_DAYS: int = Field(365, ge=0)` — 0 은 삭제 안 함, 음수는 기동 시 `ValidationError`. 정책은 새 클래스 `AccessLogRetentionService`(`app/features/home/services/access_log_retention_service.py`, `BaseService`)가 맡는다 — 보존 일수·시계(`Callable[[], datetime]`)·배치 크기(기본 5,000)를 생성자로 받고 `purge()` 가 `created_at < clock() - N일` 인 행을 배치마다 커밋하며 지운 총 수를 돌려준다(정확히 N일 전 행은 남는다). 쿼리는 `UserAccessLogRepository.delete_created_before(cutoff, limit)` — `created_at` 오름차순으로 id 를 `limit` 개 고른 뒤 `DELETE ... WHERE id IN (...)`(`synchronize_session=False`). 조립은 `build_access_log_retention_service(db_session)`(설정값 + `timezone_settings.utc_now`). | 조회용 `UserAccessLogService` 와 목적이 달라(파괴적 작업·주입할 정책이 다르다) 클래스를 나눴다. MySQL 의 `DELETE ... LIMIT` 는 SQLite 에 없고, MySQL 은 `IN (SELECT ... LIMIT)` 를 받지 않는다 — 두 단계가 두 방언에서 같은 쿼리다. 고르는 쪽은 `ix_user_access_logs_created_at` 을 탄다. 배치마다 커밋해 긴 잠금·거대 undo 를 피한다. 기능 Repository 는 `_execute` 만 쓴다는 규칙(service-hardening ADR-022, `test_feature_repositories_do_not_execute_directly`)을 지키려 DML 을 `TypedReturnsRows` 로 cast 해 넘긴다. 0 이면 쿼리 없이 끝난다. | Accepted | — |
| ADR-003 | 2026-10-19 | 실행은 Celery beat. 태스크 `home.purge_expired_access_logs` 는 `app/features/home/tasks.py` 에 두고, **같은 모듈이 import 될 때** `celery_app.conf.beat_schedule["home.purge_expired_access_logs"] = {"task": ..., "schedule": crontab(hour=3, minute=30)}` 로 스스로 등록한다(중앙 `app/celery/app.py` 는 빈 `beat_schedule` 그대로, 주석만). crontab 은 `celery_app.conf.timezone = TIME_ZONE` 으로 해석된다(로컬 업무 시간대 새벽). 태스크 본문은 `background_db_session` + home provider 로 조립한다. | 태스크 자동 발견(service-hardening ADR-012)과 같은 철학 — 중앙이 기능을 import 하지 않고, 기능을 지우면 스케줄도 함께 빠진다. beat 는 기동 시 `loader.init_worker()` → `import_default_modules()` 로 include 모듈을 import 하므로(celery 5 `apps/beat.py` `init_loader` 확인) 모듈 수준 등록이 보인다. `on_after_configure` 시그널은 include 모듈이 import 되기 전에 이미 발화해 기능 쪽에서 쓸 수 없다. 운영자는 worker 와 별도로 beat 를 **하나** 띄운다(README 체크리스트 11, ARCHITECTURE §13). | Accepted | — |
| ADR-004 | 2026-10-19 | 관리 로그인 CSRF 는 synchronizer token. `AdminAuthBackend.csrf_token(request)`(정적 메서드)가 관리 세션(`admin_session`)의 `csrf_token` 을 돌려주고 없으면 `secrets.token_urlsafe(32)` 로 만든다. `create_admin_interface` 가 이 함수를 SQLAdmin 템플릿 환경 전역 `csrf_token` 으로 연결하고, 로그인 템플릿이 `<input type="hidden" name="csrf_token" value="{{ csrf_token(request) }}">` 를 그린다. `login` 은 폼을 읽은 직후 — **레이트 리밋·자격 확인보다 먼저** — 폼 값과 세션 값을 `hmac.compare_digest`(bytes)로 대조하고, 없거나 다르면 `CSRF_FAILED_MESSAGE` 로 로그인 화면을 403 으로 다시 그린다. 성공 시 기존 `session.clear()` 가 토큰을 버려 로그인마다 회전한다. 실패(400·429·403) 화면은 세션의 토큰을 그대로 싣는다(없었으면 새로 만든다) — 사용자가 바로 재시도할 수 있다. | sqladmin 0.32 의 `Admin.login` 은 GET 에서 컨텍스트 없이 `TemplateResponse(request, "sqladmin/login.html")` 만 부른다(소스 확인) — 컨텍스트를 넣을 자리가 없어 템플릿 전역 함수가 가장 단순하다. 렌더는 응답 생성 시점(`render_async`)이라 세션 변경이 `SessionMiddleware` 의 Set-Cookie 에 실린다. 레이트 리밋보다 먼저여야 위조 요청이 피해자의 시도 한도를 깎지 못한다. str 의 `compare_digest` 는 비ASCII 에서 `TypeError` 라 bytes 로 비교한다. | Accepted | — |
| ADR-005 | 2026-10-19 | 생성 시각 필터는 `app/core/admin_filters.py` 의 `LocalDateFilter` 한 클래스다. sqladmin 0.32 연산 필터 프로토콜(`has_operator=True`·`parameter_name`·`title`·`get_operation_options_for_model`·`get_filtered_query(query, operation, value, model)`·`lookups`)을 덕 타이핑으로 따르고 sqladmin 을 import 하지 않는다. 입력 `YYYY-MM-DD`(`strptime`)를 `TIME_ZONE` 의 로컬 자정으로 해석해 UTC aware 로 바꾸고, 연산 `on`(그날 0시 ≤ x < 다음날 0시)·`on_or_after`(≥ 그날 0시)·`before`(< 그날 0시). 형식 오류·0001/9999 경계 넘침·모르는 연산은 필터를 적용하지 않고 WARNING. 빠른 선택 `quick_ranges()`(오늘·최근 7일·최근 30일, 오늘 포함)는 같은 연산·값으로 만든 링크이고, 화면은 전용 템플릿 `app/templates/admin/sqladmin/filters/local_date_filter.html`(연산 select + `<input type="date">` + 빠른 선택)이 그린다. `created_at` 이 있는 7개 뷰(blog·catalog·home·reply·reports·sns·user) 모두에 붙인다. 시간대·시계는 생성자로 주입할 수 있다(테스트). | sqladmin `OperationColumnFilter` 는 `isinstance(type, DateTime)` 으로 날짜를 판정하는데 `UTCDateTime` 은 `TypeDecorator` 라 문자열이 바인딩되고 `process_bind_param` 이 거부한다(admin-login ADR-009 의 원인). 범위 조건이면 `UTCDateTime` 이 받는 aware 값만 바인딩된다. 위치는 core — 여러 기능이 쓰는 공용 부품은 core 로 올린다(service-hardening ADR-026·C-2, 기능끼리 import 금지). sqladmin 을 import 하지 않아 `ADMIN_DISABLED=true` 의 미로드 검사와 충돌하지 않는다. 템플릿의 `filter.template` 은 sqladmin 이 `{% include filter.template %}` 로 그리고, `templates_dir` 의 FileSystemLoader 가 먼저 찾는다. | Accepted | admin-login ADR-009 의 "생성 시각 필터는 뺀다" 부분 |
| ADR-006 | 2026-10-19 | **사용자 결정:** 액세스 토큰 수명 15분(`ACCESS_TOKEN_EXPIRE_MINUTES` 기본값)과 "강등·비활성화 등 권한 회수는 이미 발급된 access 토큰의 만료까지 지연"을 그대로 둔다. service-hardening R-002·R-014 에 "사용자 결정으로 수용(2026-10-19)" 을 덧붙인다. 관리 세션(서명 쿠키)의 Redis 서버 저장소 이전은 이번 범위 밖 — 사용자 결정 대기(admin-login R-001 그대로). | 상태 없는 `Principal` 설계(service-hardening ADR-017)를 유지하는 쪽을 사용자가 골랐다. 관리 세션은 요청마다 DB 를 확인해 권한 회수가 즉시 반영되므로(admin-login ADR-002) 이번 결정과 독립이다. | Accepted | — |

## 4. 불가침 제약

- **C-1**: 앱의 SQLAlchemy 엔진은 `app/core/db/session.py` 에서만 만들고, 만들 때마다 `hide_parameters=True` 를 준다(`test_engines_are_created_only_in_the_session_module`).
- **C-2**: 관리 화면에서 `UTCDateTime` 컬럼을 거르는 필터는 `LocalDateFilter` 다 — sqladmin 연산 필터를 그 컬럼에 걸지 않는다. `created_at` 이 있는 뷰는 이 필터를 가진다(`test_every_view_with_created_at_has_the_date_filter`).
- **C-3**: 관리 로그인의 CSRF 대조는 레이트 리밋·자격 확인보다 먼저다.
- **C-4**: 선행 그룹의 Active 불가침 제약(`service-hardening` C-1~C-8·C-10, `admin-login` C-1~C-5, `log-redaction-fixes` C-1~C-5, `access-policy` C-1~C-3)을 계승한다.

## 5. 변경 이력

- v0.1 (2026-10-19): 최초 작성. REQ-001(A~D)·REQ-002, ADR-001~006, C-1~C-4.
