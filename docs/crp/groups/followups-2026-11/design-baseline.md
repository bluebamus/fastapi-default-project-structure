# Design Baseline — followups-2026-11 (기준 설계 문서)

> 요구사항·설계 결정의 단일 기준. append-only.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [ ] **보통(Balanced)**
- [x] **간략(Lean)** — 지시서로 범위가 확정돼 질문 없이 진행, 사후 보고.

선택: **간략** · 선택일: 2026-11-12 · 변경 이력: 없음

## 1. 목적 / 배경
2026-11-11 정리로 실제 MySQL 자동 검증이 0건이 됐다. CI 전용 MySQL 최소 검증을 되살리고, 커버리지
TOTAL 오염과 로그 테스트의 순서 의존을 고친다.

## 2. 요구사항 레지스터

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-11-12 | TOTAL 에 테스트 파일이 섞인다, OS 무관하게 빼라(fail_under 유지) | INV-1 | Active | F-001, ADR-001 |
| REQ-002 | 2026-11-12 | `-k log` 에서 debug 상세 테스트 2건 실패, 원인 찾아 격리 수정 | INV-2 | Active | F-002, F-003 |
| REQ-003 | 2026-11-12 | CI 전용 MySQL 8.4 최소 검증(`tests/mysql`, 평소 미수집, 변수 없으면 실패) | INV-3 | Active | ADR-002 |

## 3. 설계 결정 기록

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-11-12 | `addopts` 에 `--cov-config=pyproject.toml` | pytest-cov 기본값(.coveragerc)이 없으면 자식 프로세스가 자기 cwd 에서 설정을 찾는다 — omit 패턴 자체는 Windows 에서도 맞는다 | Accepted |  |
| ADR-002 | 2026-11-12 | `norecursedirs` 로 `tests/mysql` 미수집, 접속은 `MYSQL_TEST_URL` 하나 | skip·deselect 는 게이트가 실패로 본다 | Accepted |  |
| ADR-003 | 2026-11-12 | 읽기 라우팅 검증은 같은 서버를 reader 로 쓴다 | CI 에 복제본이 없다 — 증명 범위는 테스트 docstring | Accepted |  |

## 4. 불가침 제약
- C-1: `fail_under` 는 바꾸지 않는다 — REQ-001.
- C-2: 이 PC 에서 MySQL 에 접속하지 않는다. MySQL 테스트는 수집 확인까지만 — REQ-003.
- C-3: compose 를 다시 만들지 않는다 — REQ-003.

## 5. 변경 이력
- v1.0 (2026-11-12): 최초 작성.
