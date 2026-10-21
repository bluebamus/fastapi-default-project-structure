# Run Log — admin-login (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안
> 바뀌었으면 동일 요청은 "할 일 없음".

작업 기준선 base SHA: `b5495a0` (main, 그룹 개설 직전). 브랜치 `feat/admin-login`.

## 라운드 기록

### Round 1 — 2026-10-12 · 원 명세 (관리 화면 로그인 · Bootstrap · 배포 전 할 일 · Celery include)
- **트리거:** REQ-001
- **검수 범위:** SQLAdmin 0.32 의 `AuthenticationBackend`·`login_required`·`Admin.login/logout`·템플릿 로더(`init_templating_engine`),
  starlette `SessionMiddleware`, 기존 `AuthService.authenticate`·`RateLimiter`·`ClientIPResolver`·`create_superuser`, 설정 검사·기동 로그,
  "배포 전 할 일" 4항목이 나오는 모든 문서·주석(grep)
- **결정:** ADR-001~004·007·008. 명세 대비 차이 — Redis 를 쓰는 협력 객체는 요청 시점 팩토리로 주입(ADR-001), 400 화면을
  백엔드가 직접 그림(한국어 문구)
- **신규 finding:** HIGH 1(F-001) · LOW 2(F-002·F-004) — 전부 Fixed
- **실기동 스모크:** 저장소 밖 런처가 앱 엔진을 SQLite 파일 DB 로 바꿔 끼우고(작업 디렉터리를 저장소 밖에 두어 `.env` 를 읽지 않음,
  설정은 환경 변수로만, 비밀 값은 매번 생성·출력 안 함) `create_superuser`(`--password-stdin`)로 계정을 만든 뒤 uvicorn 을
  127.0.0.1:18765 에 띄웠다. Redis 는 저장소 밖 fakeredis TCP(127.0.0.1:6390). curl 쿠키 jar 결과:
  `/health` 200 · `GET /admin/` 302 · `GET /admin/login` 200 · 틀린 비밀번호 400 · 맞는 비밀번호 302(`admin_session` 저장) ·
  `GET /admin/` 200 · `/admin/logout` 302 · 다시 `GET /admin/` 302 · `/api/v1/auth/me` 401. 종료 후 포트 해제 확인
- **수렴 판정:** `CONVERGED`

### Round 2 — 2026-10-12 · 추가 명세 (ADMIN_DISABLED · 세션 범위 · 안내서 · 모든 문서)
- **트리거:** REQ-002·REQ-003
- **세션 범위 확인:** 감독자 가정과 일치 — `request.session` 사용처는 `app/features/auth/admin_backend.py` 하나, 메인 앱에
  `SessionMiddleware` 없음, `SESSION_COOKIE_NAME` 은 `user_info_middleware.py` 가 접속 로그 `session_id` 로만 읽는다,
  `SESSION_SECRET_KEY` 소비처는 관리 세션 서명 + 설정 검사(예시 값·길이·`REQUIRED_WITHOUT_ENV_FILE`)뿐 → ADR-006
- **결정:** ADR-005·006, ADR-008 보강
- **신규 finding:** MED 1(F-003) — Fixed
- **안내서:** `docs/guides/workflows/admin-authentication.html` 12절, Mermaid 도식 8개. 기존 안내서와 같은 Mermaid 11.12.0 으로 8개 전부
  `mermaid.parse` 통과(저장소 밖 node + jsdom 로 확인 — 브라우저는 이 작업 환경에서 localhost 에 닿지 않아 렌더링 화면은 보지 못했다)
- **낡은 서술 grep:** `git grep -n -E "인증 없|ADMIN=|ADMIN_ALLOW_UNAUTHENTICATED|ADMIN_UNAUTHENTICATED_ACK|unauthenticated"` —
  남은 것은 (a) Redis·MySQL·헬스 엔드포인트의 "인증 없는 접속" 같은 다른 주제, (b) 선행 그룹 CRP·ARCHITECTURE 변경 이력의 당시 기록,
  (c) 예전 `ADMIN` 잔존을 안내하는 오류 메시지·README 문제 해결·이 그룹 문서, (d) 제거를 확인하는 테스트 상수뿐이다
- **로컬 `.env` 주석:** 작업 PC 의 로컬 `.env` 에 예전 `ADMIN` 이 있어(R-004), `.env` 를 읽는 subprocess 테스트 5건
  (`tests/core/test_deployment_safety.py` 의 production import 4건·기동 1건)이 작업 트리에서는 설계대로 실패한다. 그래서 전체 검사는
  `.env` 없는 사본(추적·신규 파일만 복사, `uv sync --locked`)에서 돌렸다 — CI 와 같은 조건
- **수렴 판정:** `CONVERGED`

### Round 3 — 2026-10-12 · 감독자 확인 지시 (ModelView 필터)
- **트리거:** REQ-004
- **재현:** 로그인한 슈퍼유저로 7개 뷰의 목록 화면이 전부 `AttributeError: ... has an attribute 'parameter_name'` 로 실패
- **결정:** ADR-009. **신규 finding:** MED 1(F-005) — Fixed
- **실기동 스모크(재실행):** Round 1 흐름에 더해 목록 7개(`post`·`product`·`user-access-log`·`reply`·`sales-order`·`sns-post`·`user`) 200,
  필터 3건(`post?author=x&author_op=equals`·`user-access-log?is_bot=true`·`user?is_active=true`) 200
- **수렴 판정:** `CONVERGED` — 그룹 종료

## 검사 결과 (최종, `.env` 없는 사본)

- `pytest -m "not mysql"` — **1000 passed · 18 deselected · skipped 0** (경고 1건은 기존 `fastapi/testclient.py` 의 httpx 폐기 예고).
  Redis 가 필요한 uvicorn 수명주기 테스트는 저장소 밖 fakeredis TCP(`REDIS_PORT=6390`)로 돌렸다
- `pytest -m mysql --collect-only` — 18건 수집(신규 `test_superuser_from_script_logs_into_admin` 포함). 실행은 CI
- `ruff check` 통과 · `ruff format --check` 309 파일 · mypy(1.20.2 순수 Python 빌드) 200 파일 무결
- `scripts/review_gate.py --fast`(ENV=test) 전건 통과 — 의존성 감사(pip-audit) 포함, INV-11 공개 API 불변
- Alembic: 리비전 추가·스키마 변경 없음(`a7c9e1f3b5d6` 은 docstring 경고만)

## fail-on-revert

대상 파일을 저장소 밖(`tmp/default/admin-login/mutation-backup`)에 복사해 두고 변이를 하나씩 넣어 해당 테스트를 돌린 뒤 원본 바이트로
복원했다(복원 후 바이트 일치 단언). **26개 전부 실패(CAUGHT)**:

| 변이 | 잡은 테스트 |
|---|---|
| 로그인 시 `session.clear()` 제거 | `test_login_replaces_preexisting_session_data` |
| `authenticate` 가 DB 확인 생략 | 강등·비활성화 2건 |
| 슈퍼유저 확인 제거 | `test_failed_login_is_400_with_one_generic_message[not-superuser]`·통합 흐름 |
| 레이트 리밋 거부 무시 / 키 접두사를 `auth:rl:login` 로 / 성공 시 초기화 제거 | 429 테스트·키 분리·카운터 초기화 |
| `SameSite=lax` / 쿠키 path `/` / 쿠키 이름 `session` / `Secure` 항상 끔 | 쿠키 속성·세션 범위·Secure 테스트 |
| logout 이 세션을 안 비움 / 재해시 커밋 제거 | logout·재해시 테스트 |
| 인증 백엔드 미주입 / 템플릿 위치 미주입 | 로그인 흐름·`main.app` 배선·화면 테스트 |
| SRI 제거 / `error` 에 safe 필터 / autocomplete 제거 | 화면 3종 |
| `main.py` 가 `ADMIN_DISABLED` 무시 / 비활성 로그에 경로 / API 설명에 `/admin` | `tests/test_admin_disabled.py` |
| 예전 `ADMIN` 검사 무력화 | 잔존 검사 7건 |
| 메인 앱에 `SessionMiddleware` | `test_main_app_has_no_session_middleware` |
| home `tasks.py` 에 import 오류 | `test_every_include_module_imports_and_registers_its_tasks` |
| 필터를 컬럼 그대로(catalog·home) / 생성 시각 연산 필터(sns) | `tests/test_admin_views_render.py` |

새 테스트 파일(`test_admin_login.py`·`test_admin_disabled.py`·`test_admin_session_scope.py`·`test_admin_views_render.py`)은 수정 전
코드(`b5495a0`)에서 `admin_backend`·`ADMIN_DISABLED` 가 없어 수집 단계부터 실패한다. 필터 테스트는 수정 전 `admin.py` 7개로
돌렸을 때 목록 7건·정의 검사·비어 있음 검사가 실패했다.

## 심각도 추세
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 1 | 0 | 1 | 0 | 2 | 3 (F-001·F-002·F-004) | CONVERGED |
| 2 | 0 | 0 | 1 | 0 | 1 (F-003) | CONVERGED |
| 3 | 0 | 0 | 1 | 0 | 1 (F-005) | CONVERGED — **그룹 종료** |
