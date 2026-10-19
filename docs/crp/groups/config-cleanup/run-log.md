# Run Log — config-cleanup (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안
> 바뀌었으면 동일 요청은 "할 일 없음".

작업 기준선 base SHA: `350fc23` (main, 그룹 개설 직전). 브랜치 `chore/config-cleanup`. 코드 커밋 `af0ec55`.

## 라운드 기록

### Round 1 — 2026-10-19 · 원 명세 (SMTP · 업로드 · SESSION_EXPIRE_SECONDS 삭제 · 만료 정본 · 사용처 계약)
- **트리거:** REQ-001(사용자 결정), REQ-002~004
- **현황(변경 전):** 12개 Settings·79필드. AST 로 읽기를 모으면 읽히지 않는 필드는 `SMTP_*` 7개(`SMTP_PASSWORD` 는 배포 검사가 읽음,
  `SMTP_TLS`·`SMTP_SSL` 은 자기 validator 만 읽음), `UPLOAD_*` 7개, `SESSION_EXPIRE_SECONDS`, 그리고 범위 밖 `API_VERSION`·
  `LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT`. 모든 클래스가 이미 `extra="ignore"`.
  `python-multipart` 는 `Request.form()` 으로 쓰인다 — `app/features/auth/admin_backend.py`(로그인 폼),
  `app/core/security/admin_session.py`(`AdminCsrfMiddleware` 의 폼 토큰), sqladmin 생성·수정 폼.
- **결정:** ADR-001~004
- **신규 finding:** LOW 4(F-001~F-004) — 전부 Fixed. 변경 후 10개 Settings·63필드.

#### 참조 목록 (`git grep -i -E "smtp|SESSION_EXPIRE_SECONDS|upload"`, 변경 전 줄 번호)

| 파일 | 참조 | 처리 |
|---|---|---|
| `config.py` | `SessionSettings` docstring 929·필드 954, `SMTPSettings` 984~1059, `UploadSettings` 1062~1117, 팩토리 1184~1192, 전역 1210~1211, `validate_deployment_safety` 1307·1324·1335~1339·1367 | 삭제. docstring 은 "관리 세션 만료는 `ADMIN_SESSION_*` 가 정한다", 검사는 `REDIS_PASSWORD` 만 남김 |
| `.env.example` | 264(주석)·276(`SESSION_EXPIRE_SECONDS`), SMTP 절 320~351, 업로드 절 353~378 | 삭제, 264 주석 고침 |
| `tests/core/test_deployment_safety.py` | 51·73(`_check` 의 smtp), 166(비밀번호 3종), 179·444(subprocess 환경), 256~265(주석·`PASSWORD_KEYS`), 277(parametrize), 317~323(`test_placeholder_smtp_password_is_rejected`), 328~331, 341 | 삭제·2종으로. Redis 빈 값 테스트는 `test_unused_redis_password_passes` 로 이름만 바꿔 유지 |
| `README.md` | 134(§2 표), 234(검사 표), 251~252(만료 행), 420(체크리스트 4), 433 | SMTP 삭제, 만료는 새 `### 세션·토큰 만료` 표로, 업그레이드 노트 신설 |
| `docs/guides/ARCHITECTURE.md` | 422(12개), 430(SMTP validator), 440, 459(`SESSION_EXPIRE_SECONDS`), 460(`smtp_settings`·`upload_settings`), 914·1015(만료 기본값), 1231·1233~1238(부록) | 삭제·10개로, 만료는 README 표를 가리킴, §16 변경 이력 1행 |
| `docs/guides/DEVELOPMENT.md` | 99, 103 | 사용처 계약 테스트 언급, `SMTP_PASSWORD` 삭제 |
| `docs/guides/server-lifecycle-guide.html` | 84(소비 지점 표·validator·배포 검사 문단), 185(부록 표·"12개·76개") | 삭제, 10개·63개, Session 행 갱신(낡은 "소비 코드 없음" 정정), Middleware 필드 수 5→6 정정 |
| `docs/guides/admin-auth-guide.html` | (세 묶음 참조 없음) §13 표의 만료 기본값 | README 표를 가리키는 한 행으로 |
| `docs/crp/groups/orm-raw-repository/design-baseline.md` | 51·105·116·190 (`SMTP_PASSWORD`) | **고치지 않음** — 이력(append-only) |
| app·scripts·migrations·`.github`·`compose.test.yaml`·`pyproject.toml` | 없음 | — |

#### fail-on-revert (변이 → 실패한 테스트)

`config.py`·테스트 파일을 작업 폴더 밖에 복사해 두고 변이 → 테스트 → 복사본으로 복원(`cmp` 일치 확인, `git checkout` 미사용).

| 변이 | 실패 |
|---|---|
| 변경 전 `config.py`(main) 그대로 | `test_every_settings_field_is_read_somewhere`(SMTP 7·UPLOAD 7·`SESSION_EXPIRE_SECONDS`), `test_removed_keys_are_ignored[SessionSettings·SMTPSettings·UploadSettings]` — 4건 |
| `UPLOAD_DIR` 필드 하나만 되살림 | `test_every_settings_field_is_read_somewhere`(`['UPLOAD_DIR']`), `test_removed_keys_are_ignored[SessionSettings]` |
| validator 본문 제외를 끔(변경 전 `config.py` 에서) | `SMTP_TLS`·`SMTP_SSL` 이 "읽힘" 으로 바뀌어 보고에서 빠진다 — 제외 규칙이 실제로 일한다 |
| `UNUSED_ALLOWED` 에 쓰이는 필드(`SESSION_SECRET_KEY`) 추가 | `test_unused_allowlist_is_not_stale` |

#### 검사

- `ruff check .` 통과 · `ruff format --check .` 326 files · mypy(격리 실행, 규칙 파일 방법) 204 source files 이상 없음.
- `pytest -m "not mysql"`: 작업 트리 **1243 passed · 0 skipped · 19 deselected**(변경 전 1232 — SMTP 테스트 2건 삭제, 새 13건).
- `.env` 없는 저장소 밖 클론(`af0ec55`, `uv sync --frozen`): **1243 passed · 0 skipped · 19 deselected**.
- `pytest -m mysql --collect-only`: 19 수집.
- `review_gate --fast`: 전건 통과(pip-audit 포함 — 네트워크 가능했음).
- alembic: 마이그레이션 변경 없음.
- HTML 2편 `html.parser` 파싱 확인.

- **수렴 판정:** `CONVERGED`
