# Charter — admin-session-hardening  (Charter v0.1 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 라운드 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 1 | `app/core/security/admin_session.py`(신규), `app/core/security/dependencies.py` | 소스 | 세션 저장소·세션 미들웨어·CSRF 미들웨어·provider |
| 1 | `app/features/auth/admin_backend.py`, `app/features/admin.py` | 소스 | 미들웨어 교체·로그인 회전·CSRF 거부 화면·로그아웃 POST 전용 |
| 1 | `app/features/user/services/user_service.py`, `app/features/user/dependencies/user_dependencies.py`, `app/features/user/admin.py` | 소스 | 즉시 폐기 훅 |
| 1 | `app/templates/admin/sqladmin/base.html`(신규) | 템플릿 | meta 토큰·인라인 스크립트 |
| 1 | `app/core/admin_filters.py`, `app/templates/admin/sqladmin/filters/local_date_filter.html` | 소스·템플릿 | 기간 필터 |
| 1 | `config.py`, `.env.example`, `pyproject.toml`, `uv.lock` | 설정·의존성 | `ADMIN_SESSION_*`, `itsdangerous` 제거 |
| 1 | `scripts/review_gate.py` | 스크립트 | 요구 ID 출처에 이 그룹 추가 |
| 1 | `tests/test_admin_session.py`·`tests/test_admin_csrf.py`(신규), `tests/admin_csrf.py`, `tests/test_admin_login.py`, `tests/test_admin_session_scope.py`, `tests/test_admin_disabled.py`, `tests/test_admin_views_render.py`, `tests/core/test_admin_date_filter.py`, `tests/test_update_noop.py`, `tests/integration/test_mysql_admin_login.py` | 테스트 | |
| 1 | `README.md`, `docs/guides/ARCHITECTURE.md`·`DEVELOPMENT.md`·`admin-auth-guide.html`(대폭 갱신), 이전 그룹 residual-risk 상태 덧붙임 | 문서 | |

## 2. 계약 (Contract)

### 2-1. 지원 구성

- `security-ops-hardening` charter §2-1 과 같다. sqladmin 0.32(라우트 구조·`sqladmin_original/` 접두사 로더·`main.js`), Starlette 1.x(미들웨어 ASGI·폼 파서), Redis 6.2 이상을 전제로 한다.

### 2-2. 위협 모델

- 방어한다: 관리 세션 쿠키의 복사·재사용(로그아웃 뒤), 세션 고정, 권한 회수(강등·비활성화·삭제) 뒤의 기존 관리 세션, 로그인 이후 관리
  화면의 CSRF(생성·수정·삭제·일괄 삭제·import·로그아웃), `<img src>` 강제 로그아웃, 관리 세션 저장소 장애 때 열림, 기간 필터 입력으로 500.
- 방어하지 않는다: JS 를 끈 브라우저의 관리 화면 쓰기(R-001), sqladmin `@action` GET(쓰지 않는 것으로 막는다, R-002), Redis 자체의
  침해(R-003), access 토큰의 즉시 폐기(service-hardening R-002·R-014, 사용자 결정), 405 `Allow` 불완전(ADR-006, 사용자 결정).

### 2-3. 불변식

- **INV-1**: 로그아웃 뒤 이전 `admin_session` 쿠키 값으로는 관리 화면에 들어갈 수 없다.
- **INV-2**: 비활성화·강등·비밀번호 변경·삭제 뒤 그 사용자의 모든 관리 세션이 Redis 에 없다(되돌려도 살아나지 않는다). API·관리 화면 어느 경로든 같다. 폐기가 실패하면 그 변경도 저장되지 않는다.
- **INV-3**: `/admin` 의 POST·PUT·PATCH·DELETE 는 세션 토큰과 같은 토큰 없이는 아무것도 바꾸지 않는다(403). GET 으로는 로그아웃되지 않는다.
- **INV-4**: 관리 세션의 수명은 로그인 뒤 `ADMIN_SESSION_MAX_AGE_SECONDS` 를 넘지 않는다.
- **INV-6**(Round 2, Round 3 에서 고침): 관리 화면에서 비활성화·비밀번호 해시 변경·삭제한 사용자의 API refresh family 는 모두 폐기되고, 강등만 된 사용자의 refresh 는 유지된다(관리 세션은 강등에서도 폐기). 일반 수정은 그대로이고, 폐기가 실패하면 변경이 저장되지 않는다.
- **INV-5**: 기간 필터는 [시작일 0시, 종료일 다음날 0시) 이고 어떤 입력도 500 을 내지 않는다.

## 3. 인수 기준 — 전부 그린

- [x] **Redis 세션** — 쿠키에 sid 만·HMAC 키·로그아웃 후 사본 거부·없는 sid 는 빈 세션 + 쿠키 삭제·로그인 회전·미사용 TTL 갱신·미사용 만료·절대 만료 상한·저장소 단위 만료·SET XX·Redis 장애 503·설정 검증 — `tests/test_admin_session.py`
- [x] **즉시 폐기** — API(비활성화·강등·삭제, 재활성화해도 안 살아남, 무관한 수정은 유지, 저장소 None)·관리 화면(비활성화·강등·비밀번호 변경·삭제는 다른 세션 키 0, 일반 수정은 유지, 자기 강등은 현재 세션도 끊김, 폐기 실패면 변경 미저장) — `tests/test_admin_session.py`
- [x] **CSRF** — 생성·수정·삭제·일괄 삭제·로그아웃 × 없음/틀림(폼·헤더)/맞음(폼·헤더), 다른 세션 토큰, 세션 없음, GET 조회 무토큰, multipart 본문 재생, GET 로그아웃 405·로그인 유지, 라우트 POST 전용, meta·스크립트, 드리프트 4건, `@action` 없음 — `tests/test_admin_csrf.py`, 로그인 CSRF 기존 테스트 — `tests/test_admin_login.py`
- [x] **기간 필터** — 경계(시작 자정 포함·종료일 23:59:59.999999 포함·다음 자정 제외)·UTC·DST·한쪽만·역순·형식 오류 — `tests/core/test_admin_date_filter.py`, 모든 `created_at` 뷰에서 기간 쿼리 200 + 실제 축소, 폼 렌더 — `tests/test_admin_views_render.py`
- [x] **세션 범위·끄기** — 메인 앱에 세션 미들웨어 없음, 하위 앱은 세션 → CSRF 순서, `ADMIN_DISABLED=true` 에서 미들웨어·저장소 없음 — `tests/test_admin_session_scope.py`, `tests/test_admin_disabled.py`
- [x] **공통 게이트** — ruff check·format, mypy, `pytest -m "not mysql"`(작업 트리 + `.env` 없는 저장소 밖 클론, skip 0), mysql 마커 수집, `review_gate` 네트워크 없는 단계, alembic 변경 없음, 실기동 스모크 — run-log
- [x] **fail-on-revert** — 변이 20건(1차 14 + 추가 범위 6) 모두 해당 테스트 실패(run-log)
- [x] **폐기 집합 정합**(Round 3) — 강등 → 관리 세션 0 + refresh 유지, 비활성화·비밀번호·삭제 → 둘 다 폐기, 변이 5건 실패(run-log Round 3)
- [x] **관리 화면 refresh 폐기**(Round 2) — 네 조건 refresh 폐기·일반 수정 유지·두 저장소 각각 실패 시 미저장 — `tests/test_admin_session.py`, 변이 2건 실패(run-log Round 2)

## 4. 변경 이력

- v0.1 (2026-10-19): 최초 작성(명세 §1~§4).
- v0.2 (2026-10-19): 감독자 추가 범위(REQ-003) — 관리 화면 폐기 조건·fail-closed 를 INV-2·인수 기준에 반영.
- v0.3 (2026-10-19): Round 2(REQ-004) — 인벤토리에 `app/features/user/admin.py`·`app/core/security/admin_session.py`·`tests/test_admin_session.py`, INV-6 "관리 화면에서 비활성화·슈퍼유저 해제·비밀번호 해시 변경·삭제한 사용자의 API refresh family 는 모두 폐기된다(일반 수정은 그대로, 실패면 변경 미저장)", 인수 기준 "관리 화면 refresh 폐기 — 네 조건 폐기·일반 수정 유지·어느 저장소 실패든 미저장, 변이 2건 실패" 를 더한다(전부 그린 — run-log Round 2).
