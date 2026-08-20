# Design Baseline — orm-raw-repository (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.

## 0. 질의 수준 (Autonomy Level) — 이 그룹의 기획 질문 깊이

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-08-13 · 변경 이력: (없음)

> 안전 하한선: 어느 수준도 파괴적·외부영향·계약변경 STOP(WORKFLOW §4 ③④)은 못 건너뛴다.

## 1. 목적 / 배경

`fastapi-default-project-structure` 가 SQLAlchemy ORM 과 `text()` 기반 Raw SQL 두 데이터 접근
방식을 **동일한 계층·트랜잭션·문서·테스트 기준**으로 제공하도록 고도화한다. 두 방식은 Repository
구현에서만 갈라지고 View→Dependency→Service→Repository 흐름, 세션 선택, 커밋 경계, Pydantic
검증, 라우터 취합, OpenAPI 품질은 동일해야 한다. 함께 애플리케이션 lifecycle(자원 관리·비동기
런타임·로깅)의 구조적 결함도 해소한다.

기준 문서 3종 (이 그룹의 상위 요구 출처):

- `docs/orm-raw-repository/2026-08-13/requirements.md` — 요구 명세 (최우선)
- `docs/orm-raw-repository/2026-08-13/development-plan.md` — 설계·실행 순서
- `docs/orm-raw-repository/2026-08-13/workflow-guide.md` — 구현 지침·예시 코드

## 2. 요구사항 레지스터 (요청 히스토리 — append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-08-13 | `docs/orm-raw-repository/2026-08-13` 문서 기반 시나리오 개발 진행, 이후 테스트·검수로 서비스에 문제 없도록 | 세 문서가 정의한 **Phase 0~7 전체** 구현 + 전체 품질 게이트 통과 | Active | ADR-001 |
| REQ-002 | 2026-08-13 | MySQL 통합 검증을 WSL 컨테이너로 고려 | MySQL 8.4 **전용 컨테이너 신규 생성**, 포트 변경(3307), 기존 3306 공유 인스턴스 무접촉 | Active | ADR-002 → **ADR-008**(포트 3308 로 정정) |
| REQ-003 | 2026-08-13 | 각 단계 진행 후 테스트·검수 수행, 버그/문제를 지속 관리해 코드 품질 유지 | Phase 종료마다 **검수 게이트 의무화**: 품질 게이트 4종 + 불변식 점검 + 발견 문제를 `ledger.md` 에 누적. Open Fix 0 이 아니면 다음 Phase 로 넘어가지 않는다 | Active | ADR-006 |
| REQ-004 | 2026-08-19 | 작업이 제대로 완료됐는지 재확인하고 준비 상태를 만들 것 | 독립 검증 패스(문서 주장 ↔ 실제 코드 대조) 수행 + MySQL 통합 환경 기동. 발견된 **거버넌스 문서 결함은 Round 8 로 처리**하고, 같은 결함이 재발하지 않도록 게이트에 기계 검사를 추가한다 | Active | ADR-008, ADR-009 |
| REQ-005 | 2026-08-20 | Raw SQL **쓰기** 워크플로를 참조 예제로 추가 (**요청 원문 미기록** — 2026-08-20 세션이 기록 전에 중단됨. 아래 내용은 미커밋 코드·주석에서 역추론했다) | SCN-RAW-002(테스트 fixture 검증)를 넘어 **운영 공개 API 로 Raw DML 워크플로를 신설**한다 — 집계 스냅샷 재적재 엔드포인트 · Raw 정렬 식별자 allowlist · deprecated 세션 별칭 제거 | Active | ADR-010 ~ ADR-014 |
| REQ-006 | 2026-08-20 | 남은 작업이 있는지 확인하고, 있으면 순서대로 정리해 진행할 것 (게이트 검사 추가 포함) | charter §3 인수기준 12칸을 **근거와 함께** 닫고, 근거가 없던 INV-10 검사를 신설한다. 같은 어긋남이 재발하지 않도록 게이트가 기계로 검사한다 | Active | ADR-015 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-08-13 | 작업 범위는 문서 전체 Phase 0~7. MIG-002 의 단계 순서를 유지한다. | 순서를 바꾸면 세션 명명 전환(Phase 1)이 Phase 5 예제 코드를 두 번 건드린다. | Accepted | — |
| ADR-002 | 2026-08-13 | MySQL 통합 검증은 `compose.test.yaml` 의 **전용 `mysql:8.4` 컨테이너, 호스트 포트 3307**. WSL Docker 로 기동하고 Windows 측 pytest 가 `127.0.0.1:3307` 로 접속한다. | 3306 은 타 프로젝트와 공유되는 `percona-mysql-8.4` 가 점유. 공유 자원 변경 없이 격리 검증 확보. Windows→WSL localhost forwarding 도달 실측 완료. | **Superseded** (→ ADR-008) | — |
| ADR-003 | 2026-08-13 | Raw 원본 테이블명은 **`sales_orders`** 로 확정. | requirements SCN-RAW-001 및 plan Phase 5 가 `sales_orders` 로 명시. workflow-guide §4.3 의 `orders` 는 예시 오기로 판단하며 요구 명세가 우선한다. | Accepted | — |
| ADR-004 | 2026-08-13 | Phase 1 의 로깅 계약 파괴(production/staging 파일 핸들러 제거, Queue 전환)를 승인 범위에 포함한다. 단 **독립 커밋**으로 분리하고 `tests/utils/test_logs.py` 를 재작성한다. | NFR-009 가 명시적으로 요구. 되돌리기 쉽도록 커밋을 분리한다. | Accepted | — |
| ADR-005 | 2026-08-13 | 기준선 테스트 수는 **201개**로 확정. | 인코딩 결함 수정 후 실측: 201 collected / 201 passed. 문서의 "201개" 와 일치. | Accepted | — |
| ADR-007 | 2026-08-13 | `BaseRepository` 의 **사용처 0건인 고급 메서드 20종**(eager loading·partial column·batch·join·bulk·upsert)을 Phase 3 에서 제거한다. 실제 호출처가 있는 `get_all`·`get_one`·`update`·`delete` 만 deprecated 별칭으로 남긴다. | ORM-REP-002 가 최소 공개 API 8개를 정식 계약으로 확정했고, ORM-REP-005 는 공통성이 확인된 경우만 Base 에 두라고 요구한다. MIG-002 의 단계적 제거는 **호출처가 있는** 이름을 위한 절차이며, Phase 0 조사에서 사용처 0건이 확인된 코드에는 유예의 목적이 없다. 필요해지면 git 이력에서 복구하거나 기능 Repository 가 명시적 메서드로 소유한다. | Accepted | — |
| ADR-006 | 2026-08-13 | Phase 종료마다 **검수 게이트**를 통과해야 다음 Phase 로 넘어간다. 게이트 = ①pytest 전건 통과 ②ruff check ③ruff format --check ④mypy ⑤해당 Phase 의 불변식 점검 ⑥`baseline/openapi.json` 대비 기존 30개 operation 불변 ⑦ledger Open Fix 0. | 단계마다 검수하지 않으면 결함이 다음 단계 코드에 섞여 원인 격리가 불가능해진다. 발견 문제는 즉시 ledger 에 기록해 "나중에" 로 흘리지 않는다. | Accepted | — |
| ADR-008 | 2026-08-19 | MySQL 통합 검증의 호스트 포트는 **3308** 이다. ADR-002 의 3307 을 대체한다. | 3307 은 IDE(VS Code)의 포트 포워딩이 선점하는 경우가 있어, 접속이 조용히 **다른 MySQL** 로 가고 증상은 "Access denied" 로만 보인다(F-012 실측). 결정 자체가 바뀐 것이므로 ADR-002 를 덮어쓰지 않고 supersede 한다. | Accepted | **ADR-002** |
| ADR-009 | 2026-08-19 | 문서가 인용하는 **커밋 해시와 MySQL 테스트 포트**를 검수 게이트가 기계로 검사한다(게이트 항목 7·8). | F-012 는 포트를 바꿨지만 charter·ADR 은 3307 로 남았고, author rewrite 는 인용 해시 12건을 한꺼번에 무효화했는데 어느 검사도 잡지 못했다. 사람이 문서를 눈으로 맞추는 절차는 이미 두 번 실패했다 — 검사로 만든다. 얕은 클론에서는 해시 검사를 skip 한다(CI 오탐 방지). | Accepted | — |
| ADR-010 | 2026-08-20 | Raw 쓰기 시나리오 **SCN-RAW-003 을 신설**하고, 운영 공개 API (`POST /api/v1/reports/sales/daily/snapshots`)로 확대한다. 원본 `requirements.md` 는 **고치지 않는다** — SCN-RAW-003 의 소유자는 이 문서(REQ-005)다. | SCN-RAW-002 는 "운영 공개 API 가 아니어도 테스트 fixture 에서 검증하라"이지 공개를 **금지**하지 않는다. 참조 예제의 목적상 읽기(SCN-RAW-001)만 공개 API 이면 Raw 쓰기의 세션 선택·커밋 경계를 보여줄 자리가 없다. 원본 명세를 사후에 고치면 "요구를 코드에 맞춘" 것이 되므로, 확장은 append-only 인 여기에 쌓는다. | Accepted | — |
| ADR-011 | 2026-08-20 | 스냅샷 재적재는 표준 SQL `DELETE` + `INSERT ... SELECT` 두 문장으로 한다. 방언 UPSERT(`ON DUPLICATE KEY UPDATE` / `ON CONFLICT`)를 쓰지 않는다. | 단위 테스트(SQLite)와 통합 테스트(MySQL)가 **같은 문장**을 검증해야 예제가 두 벌로 갈라지지 않는다. R-002(방언 이식성 비보장)와 모순되지 않는다 — 목적이 이식성 보장이 아니라 테스트 등가성이다. 두 문장은 한 트랜잭션이어야 하며 (DELETE 만 커밋되면 그 기간 리포트가 사라진다) 커밋은 View 본문이 1회 한다(C-2). | Accepted | — |
| ADR-012 | 2026-08-20 | `sales_daily_snapshots` 의 기본키는 **자연키 `sales_date`**. UUID 대리키를 쓰지 않으므로 `UUIDCreatedModel` 이 아니라 `Base` 를 직접 상속한다. | 행 하나가 곧 하루라 하루가 유일 키다. 대리키를 얹으면 "같은 날짜 두 줄"이 스키마상 가능해지고, 리포트가 두 배로 보이는 사고를 스키마가 막지 못한다. `generated_at` 은 Mixin default 가 아니라 SQL 바인드 파라미터로 채운다 — Raw DML 은 ORM/Core 의 default 를 우회하므로 Mixin 을 쓰면 조용히 NULL 이 된다. | Accepted | — |
| ADR-013 | 2026-08-20 | Raw 정렬의 **식별자 allowlist 는 Repository 가 소유**한다. View 의 쿼리 파라미터 enum 을 방어선으로 삼지 않는다. | 컬럼명·정렬 방향은 bind parameter 가 될 수 없어 문자열로 끼워 넣을 수밖에 없고, 끼워 넣는 값이 요청값이면 injection 이다(RAW-REP-004). alias 를 소유한 계층이 방어선이어야 Celery 태스크나 스크립트가 Repository 를 **직접** 호출할 때도 같은 제약이 걸린다. View 의 enum 은 UX 이지 방어가 아니다. | Accepted | — |
| ADR-014 | 2026-08-20 | 코드·문서가 인용하는 **요구 ID 의 실재를 검수 게이트가 기계 검사**한다(검사 9). 인용처는 `requirements.md` 와 이 문서 §2·§3 의 합집합이다. | F-022 로 드러난 세 번째 dangling reference 다 — 포트(F-019)·해시(F-020)에 이어 이번엔 존재하지 않는 `SCN-RAW-003` 을 코드 주석 3곳이 근거로 인용했다. 따라갈 수 없는 인용은 근거가 아니다. 같은 실패가 세 번 났으면 사람의 주의력이 아니라 검사로 막는다 (ADR-009 와 같은 원리). | Accepted | — |
| ADR-015 | 2026-08-20 | charter §3 인수기준이 **열린 채로 수렴을 선언하지 않았는지** 게이트가 검사한다(검사 11). | F-024 로 드러난 **네 번째** 문서 정합 결함이다 — 포트(F-019)·해시(F-020)·요구 ID(F-022)에 이어 이번엔 charter §3 의 12칸이 전부 열린 채 checklist 는 "미닫힘 항목 0개", run-log 는 9개 라운드 내내 `GATE 3 ☑` 였다. 두 문서가 서로를 반박하면 읽는 사람은 편한 쪽을 믿는다. 실제로 그 사이에 **INV-10 은 검사가 존재한 적조차 없었다**(F-025) — 열린 상자가 우연히 정직했던 것이고, 닫힌 상자였다면 영영 못 봤다. 사람이 눈으로 맞추는 절차는 이 그룹에서만 네 번, 자매 저장소까지 다섯 번 실패했다. | Accepted | — |

## 4. 불가침 제약 (INVARIANT REQUIREMENTS — 추가 작업이 위반 금지)

- **C-1**: 기존 공개 API 경로·응답 schema·상태 코드를 의도 없이 변경하지 않는다 (NFR-005).
- **C-2**: Repository 와 Dependency 는 commit 하지 않는다. 쓰기 커밋은 View 본문에서 응답 전 정확히 1회 (TX-001/TX-004).
- **C-3**: Raw SQL 의 외부 값은 named bind parameter, 식별자는 코드 소유 allowlist (RAW-REP-003/004).
- **C-4**: ORM Base 와 Raw Base 사이에 상속 관계를 만들지 않는다 (AR-003).
- **C-5**: 기존 세션·Repository 호환 이름은 전체 호출부 전환·사용처 0건 확인 전에 삭제하지 않는다 (MIG-002, ORM-REP-007).
- **C-6**: shutdown 에서 DB table 을 drop 하지 않는다 (AR-006).
- **C-7**: 3306 의 공유 `percona-mysql-8.4` 인스턴스를 변경하지 않는다 (REQ-002).
- **C-8**: 기존 ADMIN 정책(선택 A — 기본값 true, 인증 백엔드 없음)을 변경하지 않는다. 별도 승인 사항.
- **C-9**: JWT 인증 정책과 Redis API client 는 이번 범위 밖 (requirements §4.5/§4.6, §17).

## 5. 변경 이력

- v0.1 (2026-08-13): 최초 작성. REQ-001/002, ADR-001~005, C-1~C-9 등록.
- v0.2 (2026-08-19): REQ-004 등록. ADR-002(포트 3307) → **ADR-008**(3308) 로 supersede,
  ADR-009(문서-코드 정합 게이트) 추가. 근거: Round 8 의 F-019 · F-020.
- v0.3 (2026-08-20): REQ-005 등록(요청 원문 유실 — 코드에서 역추론). ADR-010(SCN-RAW-003 신설·공개 API 확대), ADR-011(표준 SQL 재적재), ADR-012(자연키), ADR-013(allowlist 소유 계층), ADR-014(요구 ID 인용 검사) 추가. 근거: Round 9 의 F-021 · F-022.
- v0.4 (2026-08-20): REQ-006 등록. ADR-015(charter 인수기준 ↔ 수렴 선언 정합 검사) 추가. 근거: Round 10 의 F-024 · F-025.

---
> **연동:** charter 의 계약/불변식은 이 문서의 Active 요구사항·불가침 제약과 **모순되면 안 된다**
> (모순 시 design-baseline 이 우선 — charter 를 고친다). run-log 는 라운드별로 어떤 Req/ADR 를
> 충족·참조했는지 적는다.
