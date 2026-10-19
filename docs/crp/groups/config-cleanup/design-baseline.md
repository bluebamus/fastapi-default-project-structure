# Design Baseline — config-cleanup (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태(Active/Superseded)만 바꾼다.
>
> **ID 범위:** `REQ-0xx`·`ADR-0xx`·`C-x`·`F-0xx`·`R-0xx` 는 **이 그룹 안에서만** 번호를 매긴다. 그룹 밖에서 인용할 때는
> `config-cleanup ADR-0xx` 처럼 그룹 이름을 붙인다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-19 · 변경 이력: (없음)

## 1. 목적 / 배경

`SMTPSettings`(8필드)·`UploadSettings`(7필드)·`SessionSettings.SESSION_EXPIRE_SECONDS` 는 정의만 있고 app 코드에서 읽는 곳이 없었다.
`SMTP_PASSWORD` 는 배포 안전 검사가 예시 값인지 볼 때만 읽었다. 특히 `SESSION_EXPIRE_SECONDS`(기본 24시간)는 세션 만료를 정하는 것처럼
보였지만 실제 만료는 `ADMIN_SESSION_MAX_AGE_SECONDS`(8시간)·`ADMIN_SESSION_IDLE_SECONDS`(30분)·`ACCESS_TOKEN_EXPIRE_MINUTES`(15분)·
`REFRESH_TOKEN_EXPIRE_DAYS`(7일)가 정한다. 사용자 결정으로 세 묶음을 지우고, 실제 만료 설정을 정본으로 문서에 모은다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-19 | "smtp는 삭제해줘." / `SESSION_EXPIRE_SECONDS` → "삭제, 기존 만료 설정을 정본으로" / `UPLOAD_*` → "삭제". "세션 만료 시간 설정은 있어야 한다" | 세 묶음의 필드·클래스·export·싱글턴·`.env.example` 절·배포 검사 항목·관련 테스트 삭제. `SESSION_COOKIE_NAME`·`SESSION_SECRET_KEY` 유지 | Active | ADR-001, ledger F-001~F-003 |
| REQ-002 | 2026-10-19 | (명세 §2) | 옛 키가 `.env` 에 남아도 기동은 깨지지 않는다(무시). 기동 거부로 만들지 않는다. README 업그레이드 노트 | Active | ADR-002 |
| REQ-003 | 2026-10-19 | (명세 §3) | 세션·토큰 만료(관리 세션 절대·미사용, API access·refresh)를 README 표 하나에 모으고 다른 문서는 가리킨다 | Active | ADR-004 |
| REQ-004 | 2026-10-19 | (명세 §4) | 사용처 없는 설정이 다시 생기지 않게 하는 계약 테스트, 예외는 사유와 함께 | Active | ADR-003, ledger F-004 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-19 | `SMTPSettings`·`UploadSettings` 는 그 묶음만 담은 클래스라 **클래스째** 지운다(팩토리 `get_smtp_settings`·`get_upload_settings`, 전역 `smtp_settings`·`upload_settings` 포함). `SESSION_EXPIRE_SECONDS` 는 필드만 지운다. `validate_deployment_safety()` 는 `smtp` 인자와 `SMTP_PASSWORD` 항목만 빼고 검사 자체(빈 값이면 건너뛰는 `REDIS_PASSWORD` 포함)는 유지한다. `python-multipart` 는 유지한다 | 사용자 결정(REQ-001). `python-multipart` 는 Starlette `Request.form()` 이 요구한다 — `AdminAuthBackend.login`(`app/features/auth/admin_backend.py`)과 `AdminCsrfMiddleware`(`app/core/security/admin_session.py`)가 폼을 파싱하고, sqladmin 생성·수정 폼도 같은 경로다 | Active | — |
| ADR-002 | 2026-10-19 | 옛 키는 **무시**한다. 10개 Settings 클래스가 모두 `extra="ignore"` 라 코드 변경 없이 성립하고, 테스트 1건(`test_removed_keys_are_ignored`)이 환경 변수·`.env` 양쪽에서 고정한다. 레거시 `ADMIN` 처럼 "남아 있으면 기동 거부" 로 만들지 **않는다** | 효과 없는 값일 뿐 보안 위험이 아니다 — `ADMIN` 은 뜻이 뒤집힌 이름이라 거부가 필요했지만(admin-login ADR-005), 이 키들은 남아도 아무 일도 하지 않는다 | Active | — |
| ADR-003 | 2026-10-19 | 사용처 계약 `tests/core/test_settings_usage.py`: app·scripts·migrations·`main.py`·`config.py` 를 AST 로 읽어 속성 접근(`x.FIELD`)과 `getattr(x, "FIELD")` 를 모으고, 모든 Settings 필드가 그 안에 있어야 한다. 자기 클래스의 `model_validator`·`field_validator` 본문 안 접근은 세지 않는다(값 검사만 하는 필드는 쓰이는 것이 아니다). property·검사 함수(`validate_deployment_safety`) 안 접근은 센다. 예외 `UNUSED_ALLOWED` = `API_VERSION`·`LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT`(사유 기재, 존치·삭제는 별도 결정) — 목록이 낡으면(필드가 없어졌거나 쓰이게 되면) 실패한다. 수집기가 죽으면 안 되므로 알려진 읽기 3건을 확인한다 | 이 저장소의 읽기 방식은 전역 객체 속성(`log_settings.X`)과 property 안 `self.X` 뿐이다(`getattr` 동적 이름·alias 없음). 이름 기반이라 다른 객체의 같은 이름 속성도 읽기로 센다(R-003) — 설정 필드 이름은 대문자 상수형이라 충돌이 사실상 없다 | Active | — |
| ADR-004 | 2026-10-19 | 세션·토큰 만료의 정본은 README `### 세션·토큰 만료` 표(대상·설정·기본값·뜻). README 환경 변수 표·운영 문단, ARCHITECTURE §6.2·§11·§12·부록, `admin-auth-guide.html` §13, `server-lifecycle-guide.html` 부록은 기본값을 다시 쓰지 않고 이 표를 가리킨다 | 같은 정보를 두 곳에 쓰면 갈라진다(사용자 원칙) | Active | — |

## 4. 불가침 제약

- **C-1**: Settings 필드는 읽는 코드와 함께 넣는다 — 정의만 있는 필드는 `test_every_settings_field_is_read_somewhere` 가 막는다.
- **C-2**: 모든 Settings 클래스는 `extra="ignore"` 를 유지한다(옛 `.env` 줄이 기동을 깨지 않게).
- **C-3**: 선행 그룹의 Active 불가침 제약(`service-hardening`, `admin-login`, `log-redaction-fixes`, `access-policy`,
  `security-ops-hardening`, `admin-session-hardening`)을 계승한다.

## 5. 변경 이력

- v0.1 (2026-10-19): 최초 작성. REQ-001~004, ADR-001~004, C-1~C-3.
