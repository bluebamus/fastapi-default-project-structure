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
| REQ-002 | 2026-08-13 | MySQL 통합 검증을 WSL 컨테이너로 고려 | MySQL 8.4 **전용 컨테이너 신규 생성**, 포트 변경(3307), 기존 3306 공유 인스턴스 무접촉 | Active | ADR-002 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-08-13 | 작업 범위는 문서 전체 Phase 0~7. MIG-002 의 단계 순서를 유지한다. | 순서를 바꾸면 세션 명명 전환(Phase 1)이 Phase 5 예제 코드를 두 번 건드린다. | Accepted | — |
| ADR-002 | 2026-08-13 | MySQL 통합 검증은 `compose.test.yaml` 의 **전용 `mysql:8.4` 컨테이너, 호스트 포트 3307**. WSL Docker 로 기동하고 Windows 측 pytest 가 `127.0.0.1:3307` 로 접속한다. | 3306 은 타 프로젝트와 공유되는 `percona-mysql-8.4` 가 점유. 공유 자원 변경 없이 격리 검증 확보. Windows→WSL localhost forwarding 도달 실측 완료. | Accepted | — |
| ADR-003 | 2026-08-13 | Raw 원본 테이블명은 **`sales_orders`** 로 확정. | requirements SCN-RAW-001 및 plan Phase 5 가 `sales_orders` 로 명시. workflow-guide §4.3 의 `orders` 는 예시 오기로 판단하며 요구 명세가 우선한다. | Accepted | — |
| ADR-004 | 2026-08-13 | Phase 1 의 로깅 계약 파괴(production/staging 파일 핸들러 제거, Queue 전환)를 승인 범위에 포함한다. 단 **독립 커밋**으로 분리하고 `tests/utils/test_logs.py` 를 재작성한다. | NFR-009 가 명시적으로 요구. 되돌리기 쉽도록 커밋을 분리한다. | Accepted | — |
| ADR-005 | 2026-08-13 | 기준선 테스트 수는 **201개**로 확정. | 인코딩 결함 수정 후 실측: 201 collected / 201 passed. 문서의 "201개" 와 일치. | Accepted | — |

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

---
> **연동:** charter 의 계약/불변식은 이 문서의 Active 요구사항·불가침 제약과 **모순되면 안 된다**
> (모순 시 design-baseline 이 우선 — charter 를 고친다). run-log 는 라운드별로 어떤 Req/ADR 를
> 충족·참조했는지 적는다.
