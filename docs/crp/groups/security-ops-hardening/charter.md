# Charter — security-ops-hardening  (Charter v0.1 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 라운드 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 1 | `app/core/db/session.py` | 소스(변경 없음) | 엔진 3곳 `hide_parameters=True` 확인 |
| 1 | `config.py`, `.env.example` | 설정 | `ACCESS_LOG_RETENTION_DAYS` |
| 1 | `app/features/home/{repositories/user_access_log_repository.py,services/access_log_retention_service.py(신규),dependencies/access_log_dependencies.py,tasks.py}`, `app/celery/app.py`(주석) | 소스 | 보존 삭제·beat 등록 |
| 1 | `app/features/auth/admin_backend.py`, `app/features/admin.py`, `app/templates/admin/sqladmin/login.html` | 소스·템플릿 | 로그인 CSRF |
| 1 | `app/core/admin_filters.py`(신규), `app/templates/admin/sqladmin/filters/local_date_filter.html`(신규), `app/features/{blog,catalog,home,reply,reports,sns,user}/admin.py` | 소스·템플릿 | 날짜 필터 |
| 1 | `scripts/review_gate.py` | 스크립트 | 요구 ID 출처에 이 그룹 추가 |
| 1 | `tests/core/test_db_hide_parameters.py`·`tests/core/test_admin_date_filter.py`·`app/features/home/tests/test_access_log_retention.py`·`tests/integration/test_mysql_access_log_retention.py`·`tests/admin_csrf.py`(신규), `tests/test_admin_login.py`·`tests/test_admin_views_render.py`·`tests/integration/test_mysql_admin_login.py` | 테스트 | |
| 1 | `README.md`, `docs/guides/ARCHITECTURE.md`·`DEVELOPMENT.md`·`admin-auth-guide.html`, 이전 그룹 residual-risk·design-baseline 상태 덧붙임 | 문서 | |

## 2. 계약 (Contract)

### 2-1. 지원 구성

- `access-policy` charter §2-1 과 같다. sqladmin 0.32(로그인 렌더 경로·필터 프로토콜), Celery 5(beat 의 include import)를 전제로 한다.

### 2-2. 위협 모델

- 방어한다: 드라이버 예외 문자열·로그로 바인드 값(이메일·해시·토큰)이 새는 것, 접속 로그 원문의 무기한 보존, 로그인 CSRF
  (피해자를 공격자 계정으로 로그인시키기)와 위조 요청으로 피해자의 로그인 시도 한도를 소진시키는 것, 관리 목록 날짜 입력으로
  500 을 내는 것.
- 방어하지 않는다: 로그인 **이후** sqladmin 이 그리는 폼·GET 로그아웃의 CSRF(R-001 — `SameSite=Strict`·`Path=/admin` 이 1차),
  관리 세션의 서버 쪽 폐기(admin-login R-001, ADR-006), access 토큰의 즉시 폐기(service-hardening R-002·R-014, ADR-006),
  beat 를 띄우지 않은 배포(R-002).

### 2-3. 불변식

- **INV-1**: 앱의 모든 엔진은 바인드 값을 예외 문자열에 싣지 않는다(C-1).
- **INV-2**: `ACCESS_LOG_RETENTION_DAYS=N>0` 이면 beat 실행 후 `created_at < now-N일` 인 접속 로그가 없고, 그 이후 행은 그대로다. `0` 이면 아무것도 지우지 않는다.
- **INV-3**: CSRF 토큰이 세션 값과 다른 로그인 POST 는 자격 확인·레이트 리밋 카운터에 닿지 않고 403 이다.
- **INV-4**: 관리 목록의 날짜 필터 입력은 어떤 값이어도 500 을 내지 않는다.

## 3. 인수 기준 — 전부 그린

- [x] **바인드 값** — SQLite 무결성 오류 문자열·앱 엔진 계약·생성 지점 고정·`logger.exception` 파이프라인 — `tests/core/test_db_hide_parameters.py`
- [x] **보존** — 경계(정확히 N일 전은 남는다)·배치 반복·배치마다 커밋·0=보존·설정 기본값/환경 변수/음수 거부·beat 등록(03:30)·provider 조립 — `app/features/home/tests/test_access_log_retention.py`, MySQL 마커 1건(`tests/integration/test_mysql_access_log_retention.py`, CI)
- [x] **CSRF** — 토큰 없음/빈 값/틀림 403(자격 확인·카운터 무접촉)·세션 없음 403·다른 세션 토큰 거부·실패 후 재시도·성공 후 회전·상수 시간 비교·GET hidden 필드, 기존 로그인 테스트·MySQL 로그인 테스트가 토큰을 실어 통과 — `tests/test_admin_login.py`
- [x] **날짜 필터** — 로컬 자정 ±1초 경계·UTC 변환·연산 3종·잘못된 입력 무시·빠른 선택 — `tests/core/test_admin_date_filter.py`, 모든 뷰 목록+날짜 필터 200·잘못된 입력 200·`created_at` 뷰 전부 적용·실제 목록 축소 — `tests/test_admin_views_render.py`
- [x] **공통 게이트** — ruff check·format, mypy, `pytest -m "not mysql"`(작업 트리 + `.env` 없는 저장소 밖 클론, skip 0), `review_gate --fast`, alembic 변경 없음, 실기동 스모크 — run-log
- [x] **fail-on-revert** — 변이 21건 모두 해당 테스트 실패(run-log)

## 4. 변경 이력

- v0.1 (2026-10-19): 최초 작성(명세 §1~§5).
