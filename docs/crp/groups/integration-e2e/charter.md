# Charter — integration-e2e  (Charter v0.1 / 2026-10-20)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 라운드 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 1 (W0) | `tests/integration/test_uvicorn_lifecycle.py`, `tests/integration/test_redis_target_guard.py`(신규) | 테스트 | Redis 대상 명시 강제, 자식 env 고정 |
| 1 (W0) | `.github/workflows/ci.yml`(gate pytest 단계 env), `compose.test.yaml`·README·ARCHITECTURE·server-lifecycle 안내서 | CI·문서 | 변수 명시, 실행 명령 |
| 1 (L1) | `app/features/auth/tests/test_endpoint.py` | 테스트 | XFF 우회 테스트가 홉 0 을 직접 고정(F-002) |
| 1 (W1) | `compose.e2e.yaml`(신규) | 환경 | MySQL 8.4 primary + GTID replica + Redis 7.4, `itest-default`, tmpfs |
| 1 (W2) | `tests/e2e/{conftest,stack,support}.py`(신규) | 하네스 | 점유·대상 검사, 비밀값, 복제, 자식 프로세스, 커버리지 장부 |
| 1 (W3) | `tests/e2e/test_zz_inventory.py`(신규) | 대조기 | 실제 앱 인벤토리 ↔ 장부 |
| 1 (W4) | `tests/e2e/test_{a_stack,b_api_matrix,c_flows,d_admin,e_faults,f_ops,zz_secrets}.py`, `tests/e2e/apps/undeclared_route.py`(신규) | 테스트 | L2~L6 |
| 1 (W5) | `pyproject.toml`·`uv.lock` | 의존성 | dev `playwright`, 마커 `e2e` |
| 1 (W6) | `.github/workflows/ci.yml` | CI | job `e2e` |
| 1 (W7) | README·DEVELOPMENT·ARCHITECTURE, 이 그룹 6파일, `scripts/review_gate.py`(요구 ID 출처) | 문서 | 실행 방법·보장 범위·새 API 추가 시 할 일 |

## 2. 계약 (Contract)

### 2-1. 지원 구성

- 로컬: Windows + WSL 안의 Docker(keepalive 하네스 관리) 또는 PATH 의 Docker. CI: GitHub `ubuntu-24.04`.
- MySQL 8.4(GTID, replica `read_only`), Redis 7.4, Python 3.14, Chromium(Playwright 1.64).

### 2-2. 위협 모델

- 방어한다: 테스트가 남의 DB·Redis 에 붙는 것(점유·대상 검사, `.env` 차단), 테스트가 안 돈 것을 통과로 읽는 것
  (skip·xfail 0 판정, deselect 분리, 인벤토리 빈 칸 0), 로그의 비밀값 원문.
- 방어하지 않는다: 하네스 밖에서 프로세스가 강제 종료돼 남은 컨테이너(수동 `down` 안내 — README), Windows 와 Linux 의 Celery
  풀 차이(solo·prefork — R-002).

### 2-3. 불변식

- **INV-1**: E2E 의 모든 접속 대상은 127.0.0.1 의 §0 포트다(`check_targets` 가 기동 전·자식마다 확인).
- **INV-2**: 실제 앱에서 뽑은 인벤토리의 모든 칸에 실행한 테스트 또는 N/A 사유가 있다.
- **INV-3**: 실행 로그 전체에 실행마다 만든 비밀값·발급 토큰 원문이 0건이다.
- **INV-4**: Redis 가 필요한 기존 통합 테스트는 접속 대상을 명시해야 돈다(W0).

## 3. 인수 기준 — 전부 그린

- [x] **W0** — `test_missing_redis_port_fails_instead_of_defaulting_to_6379`·`test_missing_redis_host_fails_too`·`test_explicit_but_unreachable_target_keeps_the_skip_policy`·`test_child_server_gets_the_checked_target_not_the_inherited_one`, fail-on-revert(run-log)
- [x] **L1 회귀** — `-m "not mysql"`·`-m mysql --mysql-required` 실패·skip 0(run-log)
- [x] **L2** — `test_b_api_matrix.py` 39 operation × 7칸 + `/docs`
- [x] **L3** — `test_c_flows.py` 시나리오 1~8
- [x] **L4** — `test_d_admin.py` 로그인·7 뷰·CSRF·로그아웃·만료·폐기·`ADMIN_DISABLED`
- [x] **L5** — `test_e_faults.py` Redis·worker·replica·primary
- [x] **L6** — `test_f_ops.py` Alembic·`create_superuser`·기동 거부·로깅, `test_zz_secrets.py`
- [x] **인벤토리 빈 칸 0** — `test_zz_inventory.py`
- [x] **CI job `e2e`** — `ci.yml`
- [x] **문서** — README·DEVELOPMENT·ARCHITECTURE

## 4. 변경 이력

- v0.1 (2026-10-20): 최초 작성(계획서 W0~W9·L1~L6).
