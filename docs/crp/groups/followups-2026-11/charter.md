# Charter — followups-2026-11  (Charter v1.0 / 2026-11-12)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순되면 design-baseline 우선.

## 1. 인벤토리 (Scope Inventory)

| 영역/하위시스템 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 커버리지 설정 | `pyproject.toml` (`addopts`·`[tool.coverage.*]`) | 설정 | REQ-001 |
| 로그 테스트 격리 | `tests/core/test_sql_logging_leak.py`, `tests/core/test_migrations.py` | 테스트 | REQ-002 |
| MySQL 검증 | `tests/mysql/` (conftest + 2 파일, 11건) | 테스트 | REQ-003 |
| 수집 범위 | `pyproject.toml` (`norecursedirs`) | 설정 | REQ-003 |
| CI | `.github/workflows/ci.yml` (`gate`·`mysql` 잡) | 설정 | REQ-003 |
| 문서 | `README.md`, `docs/DEVELOPMENT.md` | 문서 | REQ-001·003 |

- 총 테스트: 기본 수집 1211건(변화 없음) + `tests/mysql` 11건(경로 지정 시에만).

## 2. 계약 (Contract)
### 2-1. 지원 구성
- 기본 `pytest`·게이트: 외부 자원 없음(SQLite·fakeredis). `tests/mysql` 은 수집되지 않는다.
- `pytest tests/mysql`: `MYSQL_TEST_URL`(mysql URL, CREATE/DROP DATABASE 권한) 필수.
### 2-2. 위협 모델
- 방어한다: 로컬에서 남의 MySQL 에 실수로 붙는 것(기본 접속값 없음, 변수 없으면 연결 전 실패).
- 방어하지 않는다: `MYSQL_TEST_URL` 에 남의 서버를 직접 넣는 것.
### 2-3. 불변식
- INV-1: `--cov` TOTAL 은 `app/` 운영 코드만 반영한다(테스트·`__init__`·conftest 제외) — 자식 프로세스 포함.
- INV-2: 로그 테스트는 실행 순서·부분 실행(`-k`)과 무관하게 같은 결과를 낸다.
- INV-3: MySQL 테스트는 skip 없이 실패하거나 통과한다. 테스트마다 DB 를 만들고 지운다.
### 2-4. 비목표
- 실제 복제본(복제 지연·replica read_only·장애 전환) 검증, 로컬 MySQL 실행, compose 복원.

## 3. 인수 기준
- [x] 전체 pytest 실패 0·skip 0, `-k log`·해당 파일 단독 통과
- [x] ruff check·format, `review_gate --fast` 통과
- [x] INV-1 → 전체 `--cov` 보고서에 `tests\` 행 0, TOTAL 수치 비교(run-log)
- [x] INV-2 → 오염원(test_migrations) 뒤·단독·`-k log` 세 순서 모두 통과
- [x] INV-3 → `pytest tests/mysql --collect-only` 11건, 변수 없이 실행 시 setup ERROR(연결 시도 없음)
- [ ] `mysql` CI 잡 첫 실행 통과 — 이 PC 에서는 실행 금지, CI 가 판정

## 4. 변경 이력
- v1.0 (2026-11-12): 최초 작성.
