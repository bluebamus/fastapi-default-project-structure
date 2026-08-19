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

---
> **연동:** charter 의 계약/불변식은 이 문서의 Active 요구사항·불가침 제약과 **모순되면 안 된다**
> (모순 시 design-baseline 이 우선 — charter 를 고친다). run-log 는 라운드별로 어떤 Req/ADR 를
> 충족·참조했는지 적는다.
