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
| REQ-005 | 2026-10-19 | "API_VERSION 삭제" (config-cleanup-2 명세 §1) | `API_VERSION` 필드·`.env.example`·문서·테스트 참조 삭제, 경로 접두어는 코드에 고정된 그대로. 옛 키는 무시 | Active | ADR-005, ledger F-005 |
| REQ-006 | 2026-10-19 | "로그 설정은 실제로 연결" (명세 §2·§3) | `LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT` 은 콘솔 포매터 fmt·datefmt(기본 출력 불변), `LOG_CONSOLE_ENABLED=false` 면 모든 경로에서 콘솔 핸들러 없음 + 출력 전무 경고, 잘못된 포맷은 설정 오류, 마스킹 유지, 예외 목록을 비운다 | Active | ADR-006·ADR-007, ledger F-006·F-007 |
| REQ-007 | 2026-10-19 | 감독자 후속 지시: 마스킹이 `args` 를 비우면 `args` 를 푸는 외부 포매터의 줄이 logging 오류와 함께 사라지는지 확인, 있으면 고친다 | 접속 줄이 사라지지 않고 비밀값은 가려진다. 비밀값이 인자 하나 안에 있으면 그 인자만 가리고 `args` 모양 유지, 틀·인자에 걸치면 기존 방식 | Active | ADR-008, ledger F-008 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-19 | `SMTPSettings`·`UploadSettings` 는 그 묶음만 담은 클래스라 **클래스째** 지운다(팩토리 `get_smtp_settings`·`get_upload_settings`, 전역 `smtp_settings`·`upload_settings` 포함). `SESSION_EXPIRE_SECONDS` 는 필드만 지운다. `validate_deployment_safety()` 는 `smtp` 인자와 `SMTP_PASSWORD` 항목만 빼고 검사 자체(빈 값이면 건너뛰는 `REDIS_PASSWORD` 포함)는 유지한다. `python-multipart` 는 유지한다 | 사용자 결정(REQ-001). `python-multipart` 는 Starlette `Request.form()` 이 요구한다 — `AdminAuthBackend.login`(`app/features/auth/admin_backend.py`)과 `AdminCsrfMiddleware`(`app/core/security/admin_session.py`)가 폼을 파싱하고, sqladmin 생성·수정 폼도 같은 경로다 | Active | — |
| ADR-002 | 2026-10-19 | 옛 키는 **무시**한다. 10개 Settings 클래스가 모두 `extra="ignore"` 라 코드 변경 없이 성립하고, 테스트 1건(`test_removed_keys_are_ignored`)이 환경 변수·`.env` 양쪽에서 고정한다. 레거시 `ADMIN` 처럼 "남아 있으면 기동 거부" 로 만들지 **않는다** | 효과 없는 값일 뿐 보안 위험이 아니다 — `ADMIN` 은 뜻이 뒤집힌 이름이라 거부가 필요했지만(admin-login ADR-005), 이 키들은 남아도 아무 일도 하지 않는다 | Active | — |
| ADR-003 | 2026-10-19 | 사용처 계약 `tests/core/test_settings_usage.py`: app·scripts·migrations·`main.py`·`config.py` 를 AST 로 읽어 속성 접근(`x.FIELD`)과 `getattr(x, "FIELD")` 를 모으고, 모든 Settings 필드가 그 안에 있어야 한다. 자기 클래스의 `model_validator`·`field_validator` 본문 안 접근은 세지 않는다(값 검사만 하는 필드는 쓰이는 것이 아니다). property·검사 함수(`validate_deployment_safety`) 안 접근은 센다. 예외 `UNUSED_ALLOWED` = `API_VERSION`·`LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT`(사유 기재, 존치·삭제는 별도 결정) — 목록이 낡으면(필드가 없어졌거나 쓰이게 되면) 실패한다. 수집기가 죽으면 안 되므로 알려진 읽기 3건을 확인한다 | 이 저장소의 읽기 방식은 전역 객체 속성(`log_settings.X`)과 property 안 `self.X` 뿐이다(`getattr` 동적 이름·alias 없음). 이름 기반이라 다른 객체의 같은 이름 속성도 읽기로 센다(R-003) — 설정 필드 이름은 대문자 상수형이라 충돌이 사실상 없다 | Superseded(예외 목록 부분만, ADR-007) | — |
| ADR-005 | 2026-10-19 | `ApiSettings` 는 `API_VERSION` 하나만 담아 **클래스째** 지운다(팩토리 `get_api_settings`·전역 `api_settings` 포함). `/api/v1` 접두어는 각 기능 `router.py` 선언 그대로 둔다. 옛 키는 ADR-002 와 같이 무시(`REMOVED_KEYS` 에 추가) | 사용자 결정(REQ-005). 빈 Settings 클래스는 읽을 것이 없다 | Active | — |
| ADR-006 | 2026-10-19 | ① 콘솔 포매터 인자는 `console_formatter_kwargs()`(`app/utils/logs/config.py`) 하나가 만든다 — fmt=`LOG_CONSOLE_FORMAT`, datefmt=`LOG_DATE_FORMAT`, UTC·밀리초는 ENV. `LOG_CONSOLE_FORMAT` 기본값을 기존 고정 `LOG_FORMAT` 으로 바꾸고 `LOG_FORMAT` 은 그 기본값을 가리킨다. ② `TzFormatter.formatTime` 은 datefmt 를 받아도 development 의 밀리초를 뒤에 붙인다(기본 출력 불변). ③ 콘솔 출력 여부는 `console_enabled()` 한 곳 — false 면 앱 dictConfig 는 console·error_console 을 만들지 않고(listener 위임 0), `setup.apply_console_settings()` 가 uvicorn CLI 로거 3종(`configure_logging`)과 Celery `after_setup_logger`·`after_setup_task_logger` 로거의 `StreamHandler` 를 뗀다(`FileHandler` 계열·queue 핸들러 제외). ④ uvicorn CLI·Celery 콘솔 핸들러의 포맷은 `LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT` 중 하나라도 **직접 지정**(`model_fields_set`)했을 때만 `TzFormatter` 로 바꾼다. ⑤ 앱에는 파일 출력이 없으므로 콘솔을 끄면 앱 출력이 전무하다 — `configure_logging()` 이 `sys.__stderr__` 에 `[logging] 경고: LOG_CONSOLE_ENABLED=false …` 한 줄을 쓴다. ⑥ `LOG_CONSOLE_FORMAT` validator 는 샘플 `LogRecord`(tzname·appname·classname 포함)를 표준 `logging.Formatter(style="{")` 로 한 번 포맷한다. `LOG_DATE_FORMAT` 은 빈 값만 막는다 | ① 같은 값을 경로마다 따로 만들면 갈라진다. 설정 기본값과 실제 포맷이 달랐던 것(F-007)이 그 예다. ② 기존 dev 표기(`.704`)를 유지하려면 strftime 으로는 밀리초를 낼 수 없다. ③ 명세 "경로마다 따로 판단하지 말고 한 곳에서". ④ 기본값일 때 uvicorn(`INFO:     …`)·Celery 기본 출력을 바꾸면 INV-4(기본 출력 불변)를 깬다 — 지정 여부로 가른다. ⑤ 조용히 로그를 잃지 않게(명세). queue 를 거치면 출력처가 없어 보이지 않으므로 최종 sink 에 직접 쓴다. ⑥ `TzFormatter` 를 import 하면 `formatters → config` 순환이라 같은 style·같은 추가 필드의 표준 Formatter 로 검사한다. 마스킹은 queue 적재 전 필터라 포맷과 무관하다(log-redaction ADR-001) | Active | — |
| ADR-008 | 2026-10-19 | ① `RedactingFilter` 는 메시지에 가릴 것이 있으면 먼저 `args`(tuple)의 문자열 인자만 `redact()` 해 본다 — `msg % 가린_args` 가 합친 메시지를 가린 결과와 **같으면** 그 `args` 로 바꾸고 `msg` 는 그대로 둔다. 다르면(틀·인자에 걸침, 문자열이 아닌 인자 안의 비밀값, dict args) 기존대로 합친 문자열 + `args=None`. ② `configure_logging()` 이 `uvicorn.access` 로거에도 필터를 붙인다(`UVICORN_LOGGERS`) | ① 같음 비교가 "출력이 완전히 가려졌다" 의 증명이라, 인자만 바꾸는 경로가 덜 가리는 일은 없다. ② log-redaction ADR-001 은 access 포매터가 `args` 를 직접 풀어 `uvicorn.access` 를 제외했다 — 그 결과 `uvicorn main:app` 접속 줄의 `?token=`·`?password=` 가 원문으로 나갔다(재현: run-log Round 3). 필터를 그냥 붙이면 `args=None` 으로 `AccessFormatter` 가 `TypeError` 를 내고 줄이 사라진다 — ①이 그 전제 조건이다 | Active | log-redaction ADR-001 의 `uvicorn.access` 제외 부분 |
| ADR-007 | 2026-10-19 | 사용처 계약의 예외 목록 `UNUSED_ALLOWED` 와 그 낡음 검사(`test_unused_allowlist_is_not_stale`)를 **삭제**한다. 계약은 예외 없이 "모든 필드가 읽힌다" 하나다. 수집 규칙(AST·validator 제외·알려진 읽기 확인)은 ADR-003 그대로 | 남은 4개를 지우거나(REQ-005) 연결해(REQ-006) 목록이 비었다. 빈 목록은 "필요하면 넣으라" 는 통로가 된다 — 명세 "빈 목록이 남으면 목록 자체와 그 설명을 지운다" | Active | ADR-003(예외 목록 부분) |
| ADR-004 | 2026-10-19 | 세션·토큰 만료의 정본은 README `### 세션·토큰 만료` 표(대상·설정·기본값·뜻). README 환경 변수 표·운영 문단, ARCHITECTURE §6.2·§11·§12·부록, `admin-auth-guide.html` §13, `server-lifecycle-guide.html` 부록은 기본값을 다시 쓰지 않고 이 표를 가리킨다 | 같은 정보를 두 곳에 쓰면 갈라진다(사용자 원칙) | Active | — |

## 4. 불가침 제약

- **C-1**: Settings 필드는 읽는 코드와 함께 넣는다 — 정의만 있는 필드는 `test_every_settings_field_is_read_somewhere` 가 막는다.
- **C-2**: 모든 Settings 클래스는 `extra="ignore"` 를 유지한다(옛 `.env` 줄이 기동을 깨지 않게).
- **C-3**: 선행 그룹의 Active 불가침 제약(`service-hardening`, `admin-login`, `log-redaction-fixes`, `access-policy`,
  `security-ops-hardening`, `admin-session-hardening`)을 계승한다.

## 5. 변경 이력

- v0.1 (2026-10-19): 최초 작성. REQ-001~004, ADR-001~004, C-1~C-3.
- v0.3 (2026-10-19): Round 3(fix/redaction-keeps-args). REQ-007, ADR-008.
- v0.2 (2026-10-19): Round 2(config-cleanup-2). REQ-005·006, ADR-005~007, ADR-003 예외 목록 부분 Superseded.
