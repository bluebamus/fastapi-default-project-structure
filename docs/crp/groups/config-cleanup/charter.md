# Charter — config-cleanup  (Charter v0.2 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 라운드 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 1 | `config.py` | 설정 | `SMTPSettings`·`UploadSettings` 클래스·팩토리·전역 객체, `SESSION_EXPIRE_SECONDS`, 배포 안전 검사의 `SMTP_PASSWORD` |
| 1 | `.env.example` | 설정 견본 | SMTP 절·업로드 절·`SESSION_EXPIRE_SECONDS` 줄 |
| 1 | `tests/core/test_settings_usage.py`(신규), `tests/core/test_deployment_safety.py` | 테스트 | 사용처 계약·옛 키 무시 / SMTP 항목 제거 |
| 1 | `scripts/review_gate.py` | 스크립트 | 요구 ID 출처에 이 그룹 추가 |
| 1 | `README.md`, `docs/guides/ARCHITECTURE.md`·`DEVELOPMENT.md`·`admin-auth-guide.html`·`server-lifecycle-guide.html` | 문서 | 세 묶음 삭제, 세션·토큰 만료 정본 표(README) |
| 2 | `config.py` | 설정 | `ApiSettings`(`API_VERSION`) 클래스·팩토리·전역 삭제, `LogSettings` 의 `LOG_CONSOLE_FORMAT` 기본값·검증 |
| 2 | `app/utils/logs/config.py`·`setup.py`·`formatters.py`, `app/celery/lifecycle.py` | 코드 | 콘솔 포맷·시각 형식·콘솔 출력 여부를 설정에 연결(앱·uvicorn CLI·Celery) |
| 2 | `.env.example` | 설정 견본 | API 절 삭제, LOG_* 주석을 실제 동작대로 |
| 2 | `tests/utils/test_log_settings_wiring.py`(신규), `tests/core/test_settings_usage.py` | 테스트 | 출력 줄·콘솔 끄기·검증·마스킹 / 예외 목록 삭제·`API_VERSION` 무시 |
| 2 | `README.md`, `docs/guides/ARCHITECTURE.md`·`server-lifecycle-guide.html`·`feature-development-guide.html` | 문서 | 환경 변수 표, 로깅 절(§9.2·§9.6), 부록, 버전 설정 서술 |

과거 그룹 문서(`orm-raw-repository` design-baseline 의 REQ-017·ADR-030·ADR-045·v0.16 등)에 남은 `SMTP_PASSWORD` 언급은
**이력**이다 — append-only 라 고치지 않는다. 현재 동작은 이 그룹과 코드를 따른다.

## 2. 계약 (Contract)

### 2-1. 지원 구성

- `admin-session-hardening` charter §2-1 과 같다. pydantic-settings 의 `extra="ignore"` 동작(모르는 키는 버린다)을 전제로 한다.

### 2-2. 위협 모델

- 방어한다: 읽는 코드가 없는 설정이 "켜면 동작한다" 고 오해되는 것(특히 `SESSION_EXPIRE_SECONDS` 가 세션 만료를 정한다는 오해),
  정의만 있는 설정이 다시 쌓이는 것.
- 방어하지 않는다: 운영 `.env` 에 남은 옛 `SMTP_PASSWORD` 실제 값의 파일 보관(R-002 — 무시되지만 파일에는 남는다).

### 2-3. 불변식

- **INV-1**: config.py 의 모든 Settings 필드는 app·scripts·migrations·main.py·config.py(자기 validator 제외) 어딘가에서 속성으로
  읽힌다. 예외 목록은 두지 않는다(v0.2 — 1차의 `UNUSED_ALLOWED` 는 Round 2 에서 비어 삭제).
- **INV-2**: 지운 키(`SMTP_*`·`UPLOAD_*`·`SESSION_EXPIRE_SECONDS`·`API_VERSION`)가 환경 변수·`.env` 에 남아 있어도 설정 생성은 성공하고 그 속성은 없다.
- **INV-3**: 세션·토큰 만료의 기본값과 뜻은 README `세션·토큰 만료` 표 한 곳에 있고, 다른 문서는 그 표를 가리킨다.
- **INV-4**: `LOG_CONSOLE_*` 기본값이면 앱·uvicorn CLI·Celery 의 로그 출력은 Round 2 이전과 같다.
- **INV-5**: 콘솔 출력 여부는 `console_enabled()` 한 곳에서 판단하고, 콘솔 핸들러를 만드는 모든 경로(앱 dictConfig·uvicorn CLI·
  Celery)가 따른다. 파일 핸들러는 건드리지 않는다. 출력이 모두 꺼지면 기동 때 stderr 에 경고 한 줄을 남긴다.
- **INV-6**: 비밀값 마스킹은 로그 포맷과 무관하다(사용자 포맷에서도 메시지·traceback·stack_info 가 가려진다).

## 3. 인수 기준 — 전부 그린

- [x] **삭제** — `git grep` 참조 목록 전부 처리(run-log §참조 목록), `python-multipart` 유지 근거 확인
- [x] **옛 키 무시** — 10개 Settings 클래스 × (환경 변수 + `.env`) — `test_removed_keys_are_ignored`
- [x] **사용처 계약** — `test_every_settings_field_is_read_somewhere`·`test_unused_allowlist_is_not_stale`·`test_reader_sees_known_reads`
- [x] **문서** — README 만료 표·업그레이드 노트, 다른 문서는 표를 가리킴, HTML 은 `html.parser` 로 파싱 확인
- [x] **공통 게이트** — ruff check·format, mypy, `pytest -m "not mysql"`(작업 트리 + `.env` 없는 저장소 밖 클론), `review_gate --fast`, alembic 변경 없음 — run-log
- [x] **fail-on-revert** — 원래 `config.py` 와 필드 하나 되살리기 모두 새 테스트 실패(run-log)

Round 2 (config-cleanup-2):

- [x] **`API_VERSION` 삭제** — 필드·클래스·`.env.example`·문서, 옛 키 무시 — `test_removed_keys_are_ignored`
- [x] **포맷·시각 형식 연결** — 앱 로거·uvicorn CLI·Celery 출력 줄 — `test_custom_format_*`
- [x] **기본 출력 불변** — `test_default_format_is_the_old_hardcoded_one`·`test_default_app_output_is_unchanged`·`test_default_uvicorn_cli_and_celery_output_is_unchanged`
- [x] **콘솔 끄기** — 콘솔 핸들러 0·파일 핸들러 유지·경고 한 줄 — `test_console_disabled_*`
- [x] **설정 검증** — 잘못된 포맷·빈 날짜 형식은 설정 오류 — `test_invalid_console_format_is_a_settings_error`·`test_empty_date_format_is_a_settings_error`
- [x] **마스킹 유지** — `test_redaction_holds_with_custom_format`
- [x] **예외 목록 없음** — `UNUSED_ALLOWED` 삭제, `test_every_settings_field_is_read_somewhere` 가 예외 없이 그린
- [x] **공통 게이트·fail-on-revert** — run-log Round 2

## 4. 변경 이력

- v0.1 (2026-10-19): 최초 작성(명세 §1~§6).
- v0.2 (2026-10-19): Round 2(config-cleanup-2) — 인벤토리, INV-1 예외 목록 삭제, INV-2 에 `API_VERSION`, INV-4~6, 인수 기준.
