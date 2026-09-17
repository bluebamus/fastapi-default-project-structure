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

- `docs/specs/orm-raw-repository/requirements.md` — 요구 명세 (최우선)
- `docs/specs/orm-raw-repository/development-plan.md` — 설계·실행 순서
- `docs/specs/orm-raw-repository/workflow-guide.md` — 구현 지침·예시 코드 (ADR-026 으로 복원. 현행 절차는 `docs/guides/DEVELOPMENT.md`)

## 2. 요구사항 레지스터 (요청 히스토리 — append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-08-13 | `docs/specs/orm-raw-repository` 문서 기반 시나리오 개발 진행, 이후 테스트·검수로 서비스에 문제 없도록 | 세 문서가 정의한 **Phase 0~7 전체** 구현 + 전체 품질 게이트 통과 | Active | ADR-001 |
| REQ-002 | 2026-08-13 | MySQL 통합 검증을 WSL 컨테이너로 고려 | MySQL 8.4 **전용 컨테이너 신규 생성**, 포트 변경(3307), 기존 3306 공유 인스턴스 무접촉 | Active | ADR-002 → **ADR-008**(포트 3308 로 정정) |
| REQ-003 | 2026-08-13 | 각 단계 진행 후 테스트·검수 수행, 버그/문제를 지속 관리해 코드 품질 유지 | Phase 종료마다 **검수 게이트 의무화**: 품질 게이트 4종 + 불변식 점검 + 발견 문제를 `ledger.md` 에 누적. Open Fix 0 이 아니면 다음 Phase 로 넘어가지 않는다 | Active | ADR-006 |
| REQ-004 | 2026-08-19 | 작업이 제대로 완료됐는지 재확인하고 준비 상태를 만들 것 | 독립 검증 패스(문서 주장 ↔ 실제 코드 대조) 수행 + MySQL 통합 환경 기동. 발견된 **거버넌스 문서 결함은 Round 8 로 처리**하고, 같은 결함이 재발하지 않도록 게이트에 기계 검사를 추가한다 | Active | ADR-008, ADR-009 |
| REQ-005 | 2026-08-20 | Raw SQL **쓰기** 워크플로를 참조 예제로 추가 (**요청 원문 미기록** — 2026-08-20 세션이 기록 전에 중단됨. 아래 내용은 미커밋 코드·주석에서 역추론했다) | SCN-RAW-002(테스트 fixture 검증)를 넘어 **운영 공개 API 로 Raw DML 워크플로를 신설**한다 — 집계 스냅샷 재적재 엔드포인트 · Raw 정렬 식별자 allowlist · deprecated 세션 별칭 제거 | Active | ADR-010 ~ ADR-014 |
| REQ-006 | 2026-08-20 | 남은 작업이 있는지 확인하고, 있으면 순서대로 정리해 진행할 것 (게이트 검사 추가 포함) | charter §3 인수기준 12칸을 **근거와 함께** 닫고, 근거가 없던 INV-10 검사를 신설한다. 같은 어긋남이 재발하지 않도록 게이트가 기계로 검사한다 | Active | ADR-015 |
| REQ-007 | 2026-08-25 | lifespan 의 `AsyncExitStack` 사용을 평가해 달라 → 평가 결과를 받고 "평문 `try/finally` 로 적용해 달라" | `manage_application_resources()` 의 종료 조립을 `AsyncExitStack` 등록 역순에서 **`finally` 블록의 코드 순서**로 바꾼다. 종료 순서 계약(AR-008)·자원별 timeout·실패 격리는 불변 | Active | ADR-016 |
| REQ-010 | 2026-08-27 | 전 라운드 산출물에 대한 외부 검토 계획서를 받고 "이 계획서의 타당성을 검수해 달라 — **코드의 가용성**이 가장 중요하고, **일반적으로 사용하는 방법**을 기준으로 설계·구현이 수립돼야 한다. 난해한 방식의 설계·코드는 구현되어서는 안 된다. 작업이 늘어나는 것은 상관없다" | **프로세스 종료 신뢰성**: 정상·startup 실패·취소 **모든** 종료에서 자원 정리를 끝까지 시도하고, 종료 과정의 로그가 유실되지 않는다. 구현은 **표준 라이브러리의 관용적 사용**으로 한정한다 — stdlib 가 제공하는 동작을 직접 구현하려면 ADR 로 근거를 남긴다 | Active | ADR-017 · ADR-018 · ADR-021 · ADR-020 · ADR-022 · ADR-023 · F-028~F-039 |
| REQ-011 | 2026-09-17 | "docs 의 가이드 문서를 코드 기준으로 모두 업데이트" → "requirements.md 를 날짜 폴더가 아닌 적합한 폴더에 두고 추적되게, 참조를 갱신, CI 보완" → "남은 작업 진행" | **문서·CI 정합**: `docs/guides/` 를 코드와 대조해 현행화하고 게이트가 그 경로를 검사한다. 착수 명세 3종은 날짜 없는 `docs/specs/orm-raw-repository/` 에서 추적한다. CI 는 startup 필수 자원(Redis)과 MySQL 을 `compose.test.yaml` 로 띄워 skip 0 을 유지한다 | Active | ADR-024 |
| REQ-012 | 2026-09-17 | "삭제된 문서까지 포함해 문서를 재정리·최적화. 중복은 정확한 한 문서로 모으고, 꼭 필요한 문서만 두며, 이 저장소 관점으로만(다른 저장소와 무관하게)" | **문서 통합**: 주제마다 소유 문서를 하나로 한다 — README(진입·실행·테스트·API·배포 점검·유일한 문서 색인), `docs/guides/ARCHITECTURE.md`(구조·런타임), `docs/guides/DEVELOPMENT.md`(개발 절차). 같은 내용의 HTML·Markdown 이중 보관과 다른 저장소 비교 서술을 없앤다. 삭제된 문서에서는 현재 코드로 확인되는 사실만 회수하고 파일로 되살리지 않는다. 코드 동작·게이트·테스트 기준은 약화하지 않는다 | Active | ADR-025 |
| REQ-013 | 2026-09-17 | "삭제된 HTML 안내서 두 편은 유지해 달라 — 복원해 갱신하고, 정보가 일관되도록 맞아야 하는 모든 곳을 검토·갱신하고, 통일된 문서 배치를 적용해 달라" | **문서 일관성**: 통일 배치 — README(개요·빠른 시작·유일한 문서 색인) · `docs/guides/`(ARCHITECTURE·DEVELOPMENT·`server-lifecycle-guide.html`·`feature-development-guide.html`) · `docs/specs/orm-raw-repository/` 고정 기준선 3종(`workflow-guide.md` 복원) · CRP 이력. 여러 곳에 나오는 사실(포트·환경 변수·명령·라우트 수·종료 순서/예산·CI·Python 버전·프로젝트 설명)을 코드에 맞춘다. 다른 저장소 언급을 없앤다. 런타임 동작은 바꾸지 않는다(설명 문구·`requires-python` 만). REQ-012 의 "HTML·`workflow-guide.md` 를 되살리지 않는다" 부분을 대체한다 | Active | ADR-026 |

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
| ADR-016 | 2026-08-25 | lifespan 종료 조립에서 **`AsyncExitStack` 을 제거하고 평문 `try/finally`** 를 쓴다. 종료 순서(drain → dispose → listener stop)·자원별 timeout·실패 격리 계약은 그대로다. development-plan §9.5 와 workflow-guide §11 의 "역순 등록" 구현 예시를 이 결정이 대체하며, **workflow-guide 는 코드에 맞춰 갱신**하고 원본 요구 명세(`requirements.md`)와 development-plan 은 고치지 않는다(ADR-010 과 같은 원리). | `AsyncExitStack` 의 값어치는 **획득과 해제를 짝지어** 부분 획득 실패 시 그만큼만 되돌리는 데 있다. 그런데 이 코드는 콜백 3개를 자원 획득 **이전에** 한꺼번에 등록해, 어디서 실패하든 항상 셋 다 실행됐다 — 즉 ExitStack 은 "순서 있는 콜백 리스트" 이상을 하지 않았고 평문 `try/finally` 와 의미가 동일했다. 그 대가로 등록 순서와 실행 순서가 반대가 되어 `# 3번째로 실행` 같은 주석 세 줄로 그 간극을 메우고 있었다. 실패 격리("하나가 실패해도 뒤 단계를 건너뛰지 않는다")는 ExitStack 이 아니라 `_run_cleanup()` 이 제공하므로 잃는 보장이 없다. AR-008 수용 기준이 `try/finally` 를 첫 번째 허용 형태로 명시하므로 요구 위반도 아니다. 향후 Redis 처럼 **조건부 생성** 자원이 들어오면 그때는 획득 직후 등록이 필요해지므로 ExitStack 재도입을 재평가한다. | Accepted | — |
| ADR-015 | 2026-08-20 | charter §3 인수기준이 **열린 채로 수렴을 선언하지 않았는지** 게이트가 검사한다(검사 11). | F-024 로 드러난 **네 번째** 문서 정합 결함이다 — 포트(F-019)·해시(F-020)·요구 ID(F-022)에 이어 이번엔 charter §3 의 12칸이 전부 열린 채 checklist 는 "미닫힘 항목 0개", run-log 는 9개 라운드 내내 `GATE 3 ☑` 였다. 두 문서가 서로를 반박하면 읽는 사람은 편한 쪽을 믿는다. 실제로 그 사이에 **INV-10 은 검사가 존재한 적조차 없었다**(F-025) — 열린 상자가 우연히 정직했던 것이고, 닫힌 상자였다면 영영 못 봤다. 사람이 눈으로 맞추는 절차는 이 그룹에서만 네 번, 자매 저장소까지 다섯 번 실패했다. | Accepted | — |
| ADR-017 | 2026-08-27 | lifespan 종료 조립을 **중첩 async context manager**(`async with _database(...), _background_tasks(...)`) 로 한다. 자원마다 작은 `@asynccontextmanager` 를 두고 **획득 순서대로** 진입시켜 정리가 자동으로 역순이 되게 한다. | ADR-016 이 도입한 평문 `finally` 는 첫 cleanup 에서 `CancelledError` 가 나면 **뒤 단계가 통째로 건너뛰어진다**(F-028). 같은 시나리오 실측: 중첩 `async with`·`AsyncExitStack` 은 3단계 전부 실행 + 상태 정리, 평문 `finally` 는 `['drain']` 하나뿐. `_run_cleanup()` 의 `except Exception` 은 `CancelledError`(BaseException)를 잡지 못하므로 "실패 격리를 `_run_cleanup` 이 전담한다" 는 ADR-016 의 전제가 **취소 축에서 성립하지 않았다**. `AsyncExitStack` 대신 중첩 `async with` 를 택한 이유는 ADR-016 이 지적한 **등록 역순** 가독성 문제를 구조적으로 없애면서 같은 unwind 보장을 파이썬 기본 구문으로 얻기 때문이다. 덤으로 callback 을 자원 획득 **전**에 등록해 부분 정리가 한 번도 작동하지 않던 문제도 사라진다 — 획득하지 못한 자원은 컨텍스트에 진입조차 하지 않는다. | Accepted | — (ADR-016 **보완**, 폐기 아님) |
| ADR-018 | 2026-08-27 | logging queue listener 의 **소유권을 프로세스로** 옮긴다. FastAPI lifespan 은 listener 를 멈추지 않고, `atexit` 로 프로세스 종료 시 정리한다. | lifespan 이 listener 를 멈추면 그 **뒤에** uvicorn 이 남기는 최종 로그와 **startup 실패 traceback 이 통째로 유실된다**(F-029). 실측: DB 가 꺼진 상태에서 `python main.py` 는 **14줄만 출력하고 오류 원인을 한 글자도 남기지 않는다**(같은 실패를 `uvicorn main:app` 은 195줄로 출력한다 — 그 경로는 우리 queue 를 거치지 않기 때문). F-026 은 이 현상의 **증상**(로그 한 줄의 위치)만 옮겼고 원인은 그대로 남아 있었다. `atexit` 는 프로세스 종료 정리를 위해 존재하는 표준 훅이며 CLI·직접 실행·정상 종료를 함께 포괄한다. SIGKILL 과 uvicorn `force_exit`(Ctrl+C 2회 — uvicorn 이 `lifespan.shutdown()` 을 **호출조차 하지 않는다**)은 애플리케이션 코드로 고칠 수 없어 비범위다. | Accepted | — |
| ADR-020 | 2026-08-27 | uvicorn 3종 로거는 **`run_server()` 가 `uvicorn.run(log_config=...)` 으로** 연결한다. 앱 `build_dictconfig()` 에는 uvicorn 로거를 넣지 않는다 — **대안 A 기각**. | Wave 3(ADR-018) 이후 두 실행 경로를 같은 startup 실패로 실측하니 **정확성 차이가 없다**: `python main.py` 197줄 / `uvicorn main:app` 196줄, 양쪽 모두 traceback 2건 · `Application startup failed` 1건. 남은 차이는 로그 **포맷**뿐이다. 대안 A(앱 dictConfig 에 uvicorn 로거 포함)는 그 포맷을 얻는 대가로 *우리 `configure_logging()` 이 uvicorn 것보다 나중에 적용된다* 는 uvicorn 내부 import 순서(`Config.__init__:274` → `load():435`)에 기대는 암묵적 결합을 들인다 — 우리 저장소 안에서 검증할 수 없고, uvicorn 이 시점을 바꾸면 조용히 깨지며, 가드 테스트 `test_dictconfig_has_no_per_app_loggers` 에 구멍을 내야 한다. `log_config` 은 uvicorn 이 **문서화한 공식 파라미터**이고 이미 `main.py` 가 쓰던 방식이라, 파라미터 이름만 보고도 무슨 일이 일어나는지 읽힌다. `uvicorn main:app` CLI 경로는 uvicorn 기본 포맷으로 나가지만 오류·traceback 은 그대로 보인다(ADR-018). | Accepted | — |
| ADR-021 | 2026-08-27 | 로깅 queue/listener 구성을 **`dictConfig` 네이티브 선언**(`class`/`queue`/`listener`/`handlers` 키)으로 옮기고, bounded queue 포화 시의 종료는 **`QueueListener.enqueue_sentinel()` 오버라이드**로 해결한다. | Python 3.12+ 의 `dictConfig` 는 QueueHandler 와 QueueListener 를 직접 구성한다. 현재 설정은 `"()"` 팩토리를 써서 **그 경로를 우회**하고, `setup.py` 가 전역 3개(`_queue_handler`·`_listener_targets`·`_listener`)와 이름 조회로 stdlib 가 해주는 일을 손으로 한다. 또 stdlib 의 `enqueue_sentinel()` 독스트링이 *"timeout 을 쓰고 싶으면 이 메서드를 오버라이드하라"* 고 확장 지점을 **명시**하고 있다(F-030). 이 프로젝트의 실제 필터·포매터·bounded queue 조합으로 10개 항목(핸들러 타입·maxsize 10000·커스텀 listener 주입·queue 객체 공유·필터 순서·출력·포맷·스레드 종료)을 **실측해 성립을 확인**했다. | Accepted | — |
| ADR-022 | 2026-08-27 | 기본 동작이 **즉시 종료**인 신호(`SIGTERM`, Windows 의 `SIGBREAK`)에 *로그를 비운 뒤 원래 종료 동작으로 돌아가는* 핸들러를 `configure_logging()` 시점에 건다. **`SIGINT` 은 건드리지 않는다.** | ADR-018 의 `atexit` 훅이 신호 종료 경로에서 실행되지 않는다(F-038). uvicorn 은 정상 종료를 마친 뒤 원래 핸들러를 복구하고 **잡았던 신호를 다시 올리는데**(`capture_signals()`), 복구된 것이 `SIG_DFL` 이면 프로세스가 그 자리에서 끝나 `atexit` 이 돌지 않는다. 신호별 실측: `SIGINT` → 기본 핸들러가 `KeyboardInterrupt` 를 올려 **atexit 실행됨**(exit 0), `SIGTERM`·`SIGBREAK` → `SIG_DFL` 이라 **atexit 건너뜀**(exit 3). 그래서 대상을 뒤 두 개로 한정했다 — `SIGINT` 을 가로채면 `KeyboardInterrupt` 를 기대하는 pytest·REPL·디버거가 조용히 달라진다. 핸들러는 정리 후 `SIG_DFL` 로 되돌리고 같은 신호를 다시 올린다: **삼키지 않는다.** 삼키면 `docker stop` 이 종료되지 않는 컨테이너를 만나 SIGKILL 까지 기다린다. 이미 다른 핸들러가 걸려 있으면 뺏지 않고(gunicorn·Celery 가 자기 종료 절차를 가진다), main thread 가 아니면 건너뛴다(`signal.signal` 제약). | Accepted | — |
| ADR-023 | 2026-08-27 | lifespan 종료의 **가장 마지막 단계**로 로그 큐를 flush 한다(`_log_queue()` 컨텍스트, 예산 2초). listener 를 **멈추지는 않는다** — 멈추는 것은 여전히 프로세스의 몫이다(ADR-018 유지). | `uvicorn main:app` CLI 경로에서는 ADR-022 의 신호 핸들러가 효력이 없다(F-039). uvicorn 이 `serve()` 에서 원래 핸들러를 **먼저** 스냅샷한 뒤 그 안쪽 `_serve()` 에서 `config.load()` 로 앱을 import 하므로(`uvicorn/server.py:68-77`), 우리 `configure_logging()` 은 스냅샷보다 나중이라 종료 시 복구되는 `SIG_DFL` 에 덮인다. 신호가 온 뒤에는 손쓸 방법이 없으므로 **오기 전에** 비운다. 이 경로에서 우리 큐에 들어가는 것은 앱 로그뿐이고(uvicorn 로그는 자기 핸들러로 직행 — ADR-020) 앱이 마지막으로 로그를 남기는 시점이 lifespan 종료 절차 안이므로, 여기서 비우면 잃을 것이 남지 않는다. **flush 는 stop 이 아니므로 F-029 와 충돌하지 않는다** — listener 는 그대로 살아 있다. 구현은 stdlib 계약을 그대로 쓴다: `QueueListener._monitor` 가 record 마다 `task_done()` 을 부르므로 `unfinished_tasks == 0` 이 곧 *"넣은 걸 전부 썼다"* 다. `Queue.join()` 과 **같은 조건**을 기다리되 `join()` 에는 timeout 이 없어 직접 기다린다 — timeout 없이 썼다면 listener 가 죽어 있을 때 종료가 영원히 매달렸을 것이다(F-037 과 같은 함정). 실패해도 종료를 막지 않는다(로그를 조금 잃을 뿐이다). | Accepted | — |
| ADR-024 | 2026-09-17 | ① 착수 명세 3종을 `docs/specs/orm-raw-repository/` 로 옮겨 추적한다. ② CI gate job 은 compose 의 `redis-test` 를 띄우고 `-m "not mysql"` 로 돌며, mysql 마커는 별도 `mysql` job 이 `--mysql-required` 로 실행한다. ③ `docs/guides/` 의 경로 참조는 `tests/test_docs_guides.py` 가 검사한다. | ① `.gitignore` 가 `YYYY-MM-DD/` 폴더를 로컬 작업 기록으로 제외하면서 게이트(ADR-014)가 읽는 `requirements.md` 가 저장소에서 빠졌다. ② startup 이 Redis 를 필수로 검증하게 된 뒤 gate job 에 Redis·MySQL 이 없어 skip 11건으로 charter §3 을 위반했다 (2026-08-27 부터 MySQL skip 8건으로 이미 실패 중). services: 대신 compose 를 쓰는 이유는 로컬과 같은 파일을 쓰기 위해서다. ③ 가이드는 게이트 밖이라 코드가 바뀌어도 초록불이었다. | Accepted | — |
| ADR-025 | 2026-09-17 | ① 추적 문서를 5개로 줄인다: `README.md` · `docs/guides/ARCHITECTURE.md` · `docs/guides/DEVELOPMENT.md` · `docs/specs/orm-raw-repository/requirements.md` · `docs/specs/orm-raw-repository/development-plan.md`. ② `QUICKSTART.md` → README, `LOGGING-AND-SHUTDOWN.md`·`server-lifecycle-guide.html` → ARCHITECTURE, `ORM-RAW-WORKFLOW.md`·`feature-development-guide.html`·명세의 `workflow-guide.md` → DEVELOPMENT 로 흡수하고 원본을 삭제한다(`docs/specs/orm-raw-repository/README.md` 는 README 의 문서 색인으로). ③ `requirements.md`·`development-plan.md` 는 착수 기준선이라 내용을 고치지 않는다(`requirements.md` 의 관련 지침서 경로만 갱신). ④ `tests/test_docs_guides.py` 의 경로 검사 대상에 README 를 더한다. | ① 같은 주제가 README·가이드·HTML·명세 사본에 최대 4벌 있었고 이미 서로 어긋나 있었다(README 의 종료 "전체 상한 20초"·존재하지 않는 Repository 별칭·코드가 읽지 않는 로그 포맷 설정). 한 벌만 두어야 고칠 곳이 하나다. ② `workflow-guide.md` 는 ADR-016 이 "코드에 맞춰 갱신" 하기로 한 **살아 있는 지침**이었고 그 후속 사본(`ORM-RAW-WORKFLOW.md`)과 이중으로 남아 옛 경로·옛 종료 순서를 담고 있었다. `development-plan.md` 는 requirements §18 과 이 그룹 문서들이 Phase 를 인용하므로 기준선으로 둔다(ADR-010·ADR-016 원리). ③ HTML 안내서 두 벌은 Markdown 과 같은 내용에 다른 저장소 비교 서술이 섞여 있었다. ④ 실행 절차가 README 로 옮겨 왔으므로 같은 검사 아래 둔다 — 검사 범위를 넓힐 뿐 규칙은 그대로다. | Accepted | — |
| ADR-026 | 2026-09-17 | ① 추적 문서를 통일 배치로 둔다: `README.md` · `docs/guides/ARCHITECTURE.md` · `docs/guides/DEVELOPMENT.md` · `docs/guides/server-lifecycle-guide.html` · `docs/guides/feature-development-guide.html` · `docs/specs/orm-raw-repository/{requirements,development-plan,workflow-guide}.md` · `docs/crp/groups/`. ② HTML 두 편은 흐름 요약이고 상세 표는 Markdown 이 소유한다(HTML 은 요약 후 링크). ③ 명세 3종은 고정 기준선 — 경로·이름만 고치고, 복원한 `workflow-guide.md` 에는 기준선 상태 한 줄만 더한다. ④ 설명 문구 정합: `config.API_DESCRIPTION`(UnitOfWork 서술 제거), 코드가 읽지 않는 `LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT`·`API_VERSION` 과 채우지 않는 `user_access_logs.country/country_code/city`·`request.state.user_id` 를 사실대로 적는다(필드는 유지). `.env.example` 의 `PROJECT_NAME`·`VERSION` 예시는 코드 기본값으로, `DESCRIPTION` 은 주석 예시로 둔다. ⑤ `requires-python` 을 `>=3.13` 으로 올리고 `uv.lock` 을 갱신한다. | ① ADR-025 가 HTML 두 편을 지웠으나 사용자가 유지를 요청했다(REQ-013) — ADR-025 의 ①② 중 HTML·`workflow-guide.md` 삭제 부분만 뒤집고, 주제별 소유 문서를 하나로 둔다는 원칙은 유지한다. ② 같은 표를 두 벌 두면 다시 어긋난다(ADR-025 ① 의 근거) — 그래서 HTML 은 요약·링크만 가진다. ③ requirements §1 과 이 문서 §1 이 `workflow-guide.md` 를 기준 문서로 인용한다. ④ `.env.example` 을 복사하면 `DESCRIPTION` 이 `/docs` 설명 전체를 한 줄로 덮고, `PROJECT_NAME` 예시에 오타가 있었다. 설정 필드를 지우지 않는 것은 동작·계약 테스트를 바꾸지 않기 위해서다. ⑤ `app/core/repositories/repository_base.py` 가 `typing.TypeVar(default=...)`(3.13+)를 쓴다. `.python-version`·CI 는 3.14 그대로다. | Accepted | — |

> **ADR-020 은 위 표에 확정 등록됐다(대안 A 기각).** 판단을 뒤집은 것은 실측이다 — Wave 3 이 F-029 를 닫은 뒤에는 두 실행 경로의 **정확성이 같아져**, 대안 A 를 살리던 근거 *"CLI 경로에서 오류가 안 보인다"* 가 더 이상 성립하지 않는다. 남은 이득이 포맷 하나뿐인 상태에서 남의 라이브러리 내부 순서에 기대는 결합을 새로 들일 이유가 없다. 그 결과 `build_dictconfig()` 에 `loggers` 키를 넣지 않으므로 가드 테스트도 **그대로 살아 있다**.
>
> **ADR-019 는 건너뛴다 — 재사용도 개정도 하지 않는다.** 코드·테스트 5곳이 이 번호를 "앱별 로거 미등록" 의 뜻으로 인용하지만 **근거 문서가 이 저장소에 없는 legacy ID** 다(F-023 / residual-risk R-007 / 게이트 `LEGACY_UNDECLARED_IDS`). 개정할 본문 자체가 없고, 같은 번호에 다른 결정을 담으면 그 5곳의 인용과 의미가 충돌한다. **이 문단에 번호가 적힌 탓에 게이트 검사 9 는 이제 ADR-019 를 "선언됨" 으로 본다 — 의도한 것이다.** 유령이라는 사실을 권위 있는 문서에 남기는 편이, 화이트리스트에만 숨겨 두는 것보다 낫다.

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
- v0.5 (2026-08-25): REQ-007 등록. ADR-016(lifespan 종료 조립을 `AsyncExitStack` → 평문 `try/finally`) 추가. 근거: Round 11 의 F-026.
- v0.6 (2026-08-27): REQ-010 등록. ADR-017(종료 조립 = 중첩 async context manager),
  ADR-018(logging listener 소유권을 프로세스로 + `atexit`), ADR-021(`dictConfig` 네이티브
  queue/listener + `enqueue_sentinel` 오버라이드) 추가. ADR-019 는 legacy 유령 ID 라
  **건너뛴다**. 근거: Round 12 의 F-028 ~ F-037.
- v0.7 (2026-08-27): ADR-020 확정 — uvicorn 로거는 `run_server()` 의
  `uvicorn.run(log_config=...)` 으로 연결하고 앱 `dictConfig` 에는 넣지 않는다(**대안 A 기각**).
  Wave 3 이후 두 실행 경로의 정확성이 같아졌다는 실측이 근거다. F-036(charter §2-4 와
  가드 테스트의 지시 불일치)을 함께 정정했다.
- v0.8 (2026-08-27): ADR-022 추가 — 즉시 종료형 신호(`SIGTERM`/`SIGBREAK`)에 로그를 비우고
  원래 동작으로 죽는 핸들러를 건다. **ADR-018 을 폐기하지 않는다** — `atexit` 는 정상 종료
  경로를 그대로 맡고, ADR-022 가 그것이 닿지 않는 신호 경로를 덮는다. 근거: F-038.
- v0.9 (2026-08-27): ADR-023 추가 — lifespan 종료 마지막 단계로 로그 큐를 flush 한다
  (**멈추지 않는다**). F-039(`uvicorn main:app` CLI 경로의 꼬리 유실) 종결.
  **ADR-018 을 폐기하지 않는다** — "lifespan 은 listener 를 *멈추지* 않는다" 는 그대로이고,
  "다 나갈 때까지 *기다리기*" 가 추가됐다. 사용자 결정(2026-08-27): 대안 A(수정) 채택.
  **ADR-016 은 폐기하지 않는다** — ADR-017 이 그것이 검증하지 않은 축(취소)을 보완한다.
- v0.10 (2026-09-17): REQ-011 · ADR-024 등록 — 가이드 현행화(`docs/guides/`), 착수 명세 3종을
  `docs/specs/orm-raw-repository/` 로 이동, CI 에 Redis(gate)·MySQL(job) 추가, 가이드 경로 검사 테스트.
  §기준선 문서 목록의 경로를 새 위치로 바꿨다(내용은 불변).
- v0.11 (2026-09-17): REQ-012 · ADR-025 등록 — 문서를 README·ARCHITECTURE·DEVELOPMENT + 착수 명세 2종으로
  통합. §1 기준선 목록의 `workflow-guide.md` 경로를 흡수처(`docs/guides/DEVELOPMENT.md`)로 바꿨다.
- v0.12 (2026-09-17): REQ-013 · ADR-026 등록 — HTML 안내서 두 편과 `workflow-guide.md` 복원, 통일 문서 배치,
  설명 문구·`requires-python` 정합. §1 기준선 목록의 `workflow-guide.md` 경로를 원래 위치로 되돌렸다.

---
> **연동:** charter 의 계약/불변식은 이 문서의 Active 요구사항·불가침 제약과 **모순되면 안 된다**
> (모순 시 design-baseline 이 우선 — charter 를 고친다). run-log 는 라운드별로 어떤 Req/ADR 를
> 충족·참조했는지 적는다.
