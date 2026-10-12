# Charter — admin-login  (Charter v0.2 / 2026-10-12)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 라운드 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 1 | `app/features/auth/admin_backend.py`(신규) | 소스 | `AdminAuthBackend` |
| 1 | `app/features/admin.py` | 소스 | `build_admin_auth_backend`·`_app_redis`·`ADMIN_TEMPLATES_DIR`, `create_admin_interface` 주입, docstring |
| 1 | `app/templates/admin/sqladmin/login.html`(신규) | 템플릿 | Bootstrap 5.3.8 + SRI |
| 1 | `config.py`, `main.py` | 소스 | `ADMIN_ALLOW_UNAUTHENTICATED`·배포 검사 규칙·WARNING 제거, 주석·description |
| 1 | `pyproject.toml`, `uv.lock` | 설정 | `itsdangerous` |
| 1 | `scripts/create_superuser.py`, `app/core/middlewares/client_ip.py`, `migrations/versions/a7c9e1f3b5d6_store_datetimes_as_utc_microseconds.py` | 소스(docstring) | 배포 전 할 일 — 리비전은 docstring 만, 스키마 변경 없음 |
| 1 | `tests/test_admin_login.py`(신규), `tests/integration/test_mysql_admin_login.py`(신규), `tests/core/test_celery_app.py`, `tests/core/test_deployment_safety.py` | 테스트 | |
| 2 | `config.py`(`ADMIN_DISABLED`·`validate_no_legacy_admin`·`API_DESCRIPTION`), `main.py`, `app/features/*/admin.py` docstring | 소스 | |
| 2 | `tests/test_admin_disabled.py`(신규), `tests/test_admin_session_scope.py`(신규), `tests/test_admin_wiring.py`, `tests/test_route_inventory.py` | 테스트 | |
| 2 | `docs/guides/admin-auth-guide.html`(신규) | 문서 | 도식 12절 |
| 3 | `app/features/{blog,catalog,home,reply,reports,sns,user}/admin.py`, `tests/test_admin_views_render.py`(신규) | 소스+테스트 | `column_filters` → `sqladmin.filters` |
| 공통 | `README.md`, `.env.example`, `docs/guides/ARCHITECTURE.md`·`DEVELOPMENT.md`·`server-lifecycle-guide.html`·`feature-development-guide.html`, `scripts/review_gate.py`(요구 ID 출처 목록), `docs/crp/groups/{service-hardening,orm-raw-repository}/` 상태 줄 | 문서 | |

## 2. 계약 (Contract)

### 2-1. 지원 구성

- `service-hardening` charter §2-1 과 같다. Redis 필수(관리 화면 로그인 레이트 리밋도 Redis).

### 2-2. 위협 모델

- 방어한다: 관리 화면 무단 접근(슈퍼유저 로그인), 세션 고정, 관리 화면 CSRF(SameSite=Strict), 계정 열거(단일 문구),
  무차별 대입(레이트 리밋), 쿠키 탈취·위조(HttpOnly·Secure·서명·만료·Path), 권한 회수 지연(매 요청 DB 확인),
  세션의 API 인증 유출(하위 앱 전용), 쓰지 않는 관리 화면의 노출(`ADMIN_DISABLED`), 뜻이 뒤집힌 예전 설정의 조용한 오동작.
- 방어하지 않는다: 서버 쪽 세션 폐기 목록(R-001), 로그인 폼 CSRF(R-002), CDN 차단 환경의 스타일(R-003), 2FA·SSO.

### 2-3. 불변식

- **INV-1**: `/admin` 의 모든 라우트는 활성 슈퍼유저 세션 없이는 로그인 화면으로 보낸다.
- **INV-2**: 관리 세션 쿠키는 `admin_session`·`Path=/admin`·`SameSite=Strict`·HttpOnly·8시간이고 배포 환경에서 Secure 다.
- **INV-3**: 메인 앱에 세션 미들웨어가 없고, 세션 쿠키는 API 를 인증하지 않는다.
- **INV-4**: `ADMIN_DISABLED=true` 면 관리 화면 경로·객체가 앱 어디에도 없다.
- **INV-5**: 예전 `ADMIN` 설정은 조용히 무시되지 않는다(test 외 기동 거부).

## 3. 인수 기준 — 전부 그린

- [x] **공통 게이트** — ruff check·format, mypy, `pytest -m "not mysql"` skipped 0(Redis 는 저장소 밖 fakeredis TCP), `review_gate --fast`, `-m mysql` 수집 — run-log Round 1·2
- [x] **백엔드** — 성공/틀린 비밀번호/없는 사용자/비슈퍼유저/비활성/429/강등 후 거부/logout/세션 고정/쿠키 속성/재해시 커밋 — `tests/test_admin_login.py`
- [x] **화면** — GET 200·Bootstrap+SRI·필드 name·autocomplete·레이블·이스케이프
- [x] **통합** — `create_superuser` 진입 함수(`--password-stdin`) → 302 → 400 → 302 → 200 → logout → 302, 일반 사용자 실패. `mysql` 마커로 실제 `python -m scripts.create_superuser` 같은 흐름(CI 실행, 로컬 수집만)
- [x] **설정 제거 회귀** — 확인 플래그가 코드에 없음, 배포 환경 관리 화면 켜짐 통과, 남은 `.env` 줄 무시
- [x] **Celery include import** — ADR-007
- [x] **ADMIN_DISABLED** — 404·응답 무노출·기동 로그·객체 미생성, 예전 `ADMIN` 잔존 거부
- [x] **세션 범위** — ADR-006 의 4개 테스트
- [x] **관리 화면 렌더링** — 로그인한 슈퍼유저로 모든 ModelView 목록·필터 15건·상세 1건 200(`tests/test_admin_views_render.py`), 실기동 스모크에서 목록 7개·필터 3건 200
- [x] **실기동 스모크** — uvicorn + SQLite 파일 DB + fakeredis TCP + curl 쿠키 jar(run-log Round 1·3)
- [x] **fail-on-revert** — 변이 26개 전부 해당 테스트가 실패(run-log)

## 4. 변경 이력

- v0.1 (2026-10-12): 최초 작성(원 명세).
- v0.2 (2026-10-12): 추가 명세 — `ADMIN_DISABLED`·세션 범위·안내서. 인수 기준 전부 닫음.
- v0.3 (2026-10-12): 감독자 확인 지시 — 관리 화면 렌더링(필터 객체) 인수 기준 추가·닫음.
