# Design Baseline — access-policy (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태(Active/Superseded)만 바꾼다.
>
> **ID 범위:** `REQ-0xx`·`ADR-0xx`·`C-x`·`F-0xx`·`R-0xx` 는 **이 그룹 안에서만** 번호를 매긴다. 그룹 밖에서 인용할 때는
> `access-policy ADR-0xx` 처럼 그룹 이름을 붙인다(코드 주석의 `access-policy ADR-0xx` 는 이 그룹이다).

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-13 · 변경 이력: (없음)

## 1. 목적 / 배경

예시 뷰마다 인증 의존성을 손으로 달아 왔고, 빠뜨리면 그 뷰는 조용히 공개됐다(log-redaction R-004 — "새 쓰기 엔드포인트
자동 보호 없음"). 권한 계약 테스트도 손으로 적은 목록(`OWNED`·`ADMIN_ROUTES`)만 봤다. 사용자는 인증 적용 범위와 기본
정책을 **뷰 단위 데코레이터**로 정하길 원했다. FastAPI 에서 그 데코레이터는 경로 데코레이터의 `dependencies=[...]` 이고,
데코레이터만으로는 기본 정책이 생기지 않으므로 "선언 없는 뷰가 있으면 기동 거부"로 기본 거부를 만든다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-13 | "현재 프로젝트의 view들은 예시들이다. 때문에 적절하게 판단하여 인증 적용 범위와 기본 정책을 설정해줘. 이는 데코레이터로 충분히 적용할 수 있는 것으로 알고 있다. 뷰 단위 설정으로 고려해줘." 원칙 유지: 같은 목적은 하나의 모듈 클래스, 조합은 주입, 모든 단계 단위 테스트(fail-on-revert) | 아래 REQ-001-A~D | Active | ADR-001~004, C-1~C-3 |
| REQ-001-A | 2026-10-13 | (접근 수준 선언) | 접근 수준 4개를 `Depends` 객체로 공개 — `Public`·`PublicWrite`(표식)·`LoginRequired`·`SuperuserRequired`(기존 의존성 그대로). 인자 `principal` 도 선언으로 인정 | Active | ADR-001 |
| REQ-001-B | 2026-10-13 | (기본 정책) | 앱 조립 직후 모든 `APIRoute` 를 검사해 선언 없음·이중 선언·쓰기에 `Public`·조회에 `PublicWrite` 가 있으면 위반 전체를 담아 기동을 멈춘다 | Active | ADR-003, ledger F-001 |
| REQ-001-C | 2026-10-13 | (예시 적용) | 예시 뷰 전부에 현재 동작 그대로의 수준을 뷰 단위로 선언. 응답 코드·OpenAPI 불변 | Active | ADR-002 |
| REQ-001-D | 2026-10-13 | (테스트 정리) | 손으로 적은 `OWNED`·`ADMIN_ROUTES` 를 라우트별 기대 수준 표 하나로 정리하고 실제 판정과 대조, 401/403 실요청 테스트는 그 표에서 대상을 뽑는다 | Active | ADR-004 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-13 | 접근 수준은 `app/core/security/access.py` 의 `Depends` 객체 넷이다 — `Public = Depends(public)`, `PublicWrite = Depends(public_write)`(각각 아무것도 하지 않는 고유 `async` 표식 함수), `LoginRequired = Depends(get_current_principal)`, `SuperuserRequired = Depends(require_superuser)`. 뷰는 `dependencies=[...]` 에 그대로 넣는다. 인자 `principal: CurrentPrincipal`/`SuperuserPrincipal` 도 같은 수준의 선언으로 인정한다(둘 다 적게 강제하지 않는다). **함수를 감싸는 데코레이터는 만들지 않는다.** | FastAPI 는 핸들러 시그니처로 주입·검증·OpenAPI 를 만든다 — 감싸면 그것이 가려진다. 경로 데코레이터의 `dependencies=` 가 FastAPI 에서 "데코레이터로 적용"하는 방식이다. 표식을 `async` 로 둔 이유: 동기 의존성은 스레드풀로 돈다 — 아무것도 안 하는 함수에 그 비용을 물리지 않는다. 인증 수준은 기존 의존성을 그대로 써서 401/403·`request.state.user_id`·OpenAPI security 가 그대로다. 위치는 기존 core security 패키지(기능끼리 import 금지 — service-hardening C-2). | Accepted | — |
| ADR-002 | 2026-10-13 | 예시는 **뷰 단위 선언으로 통일**한다. home·reports 의 `APIRouter(dependencies=[Depends(require_superuser)])` 는 각 뷰의 `dependencies=[SuperuserRequired]` 로 옮기고, 401/403 응답 문서 `responses=FORBIDDEN_RESPONSES` 는 라우터 단위에 남긴다. 라우터 단위·`include_router(dependencies=…)` 선언도 판정상 인정한다(의존성 트리에 들어가므로). 정책은 현재 동작 그대로(감독자 판단): blog·sns·reply 조회 `Public`·쓰기 인자 `CurrentPrincipal`(수정·삭제는 서비스 `OwnershipPolicy`), catalog 조회 `Public`·쓰기 `SuperuserRequired`, reports·접속 로그 전부 `SuperuserRequired`, user 목록·생성·삭제 `SuperuserRequired`·단건 조회/수정 인자 `CurrentPrincipal`(+본인 판정, 특권 필드는 슈퍼유저), auth `register`·`login`·`refresh`·`logout` `PublicWrite`·`/me` 는 `get_current_user`(안에서 `get_current_principal`), `/health`·`/ready`·DEBUG `/docs` `Public`. | 사용자 요구 "뷰 단위". 응답 문서를 라우터에 남겨야 OpenAPI 가 바이트 단위로 같다 — 변경 전후 `app.openapi()` 를 정렬 JSON 으로 떠 `cmp` 로 같음을 확인했다(run-log). `/me` 는 사용자 엔티티가 필요한 의존성이 이미 인증을 포함해 별도 표식을 달지 않는다(중복 선언 강제 안 함). | Accepted | — |
| ADR-003 | 2026-10-13 | 기본 정책은 **기동 시 검사** `AccessPolicyGuard`(같은 파일, 클래스 하나)다. `main.py` 가 라우터 include·health/ready·`/docs`·SQLAdmin 마운트를 마친 직후 `AccessPolicyGuard().verify(app)` 를 부른다. `routes()` 는 `fastapi.routing.iter_route_contexts(app.routes)` 로 `_IncludedRouter` 중첩을 펼친 유효 라우트 중 원본이 `APIRoute` 인 것(`include_in_schema=False` 포함)을 `"METHOD /전체/경로"` 와 함께 낸다. `levels()` 는 dependant 트리를 재귀로 훑어 표식·`get_current_principal`·`require_superuser` 를 찾고, 슈퍼유저가 있으면 로그인을 접는다. 위반: 선언 없음, 서로 다른 수준 둘 이상, 쓰기 메서드에 `Public`(→ `PublicWrite` 안내), 안전한 메서드(GET·HEAD·OPTIONS)에 `PublicWrite`. 위반이 있으면 **전부** 담은 `AccessPolicyError(RuntimeError)` 로 `main` import 가 실패한다. 제외: Starlette `Route`(FastAPI 문서 경로)·`Mount`(`/admin` — 자체 세션 인증). | 이 저장소의 설정 오류는 모듈 import 시점에 `RuntimeError` 로 멈춘다(`validate_env_source`·`validate_no_legacy_admin`·`validate_deployment_safety`) — 같은 관례. 앱 팩토리가 없고 `main` 모듈 수준에서 조립하므로 조립 끝 한 줄이 호출 지점이다. `iter_route_contexts` 는 FastAPI 0.141 의 `_IncludedRouter.effective_route_contexts`(log-redaction 조사에서 쓴 경로)를 감싼 모듈 함수로, 전체 경로·라우터 단위 의존성까지 합친 dependant 를 준다 — `app.routes` 를 직접 훑으면 하위 라우터의 경로가 상대 경로다. | Accepted | — |
| ADR-004 | 2026-10-13 | 권한 테스트의 기대 표는 `tests/test_authorization.py` 의 `EXPECTED_ACCESS`(라우트 → 수준) **하나**다. `test_route_access_levels_match_the_policy_table` 이 가드의 `levels()` 판정과 대조한다. 손으로 적은 `ADMIN_ROUTES` 는 없앴다 — 401(모든 `LoginRequired`·`SuperuserRequired`)·403(모든 `SuperuserRequired`) 실요청 테스트는 표에서 대상을 뽑는다(경로 변수는 임의 값, 본문 없음). `OWNED` 는 소유권 테스트용 요청 본문 묶음으로 남기되 대상 집합이 표의 "로그인으로 만드는 컬렉션"과 같은지 검사한다. docstring 의 권한 표는 지웠다. "모든 operation 이 분류됐는가"는 기동 검사가 맡는다. | 표가 두 벌이면 하나만 고쳐도 테스트가 초록일 수 있다. 인증 의존성은 본문·쿼리 검증보다 먼저 풀리므로(FastAPI `solve_dependencies` 순서) 401/403 은 경로 변수·본문과 무관하다 — 실측 통과. 경로 골든 `tests/test_route_inventory.py` 는 목적이 달라(공개 API 경로·메서드 불변) 그대로 둔다. | Accepted | — |

## 4. 불가침 제약

- **C-1**: 접근 수준 판정은 `AccessPolicyGuard.levels()` 한 곳이다 — 테스트도 이 함수로 판정한다(복제 판정 금지).
- **C-2**: 함수를 감싸는 인증 데코레이터를 만들지 않는다(ADR-001). 새 인증 방식(API 키 등)은 `access.py` 에 수준으로 더한다.
- **C-3**: 선행 그룹의 Active 불가침 제약(`service-hardening` C-1~C-8·C-10, `admin-login` C-1~C-5, `log-redaction-fixes` C-1~C-5)을 계승한다.

## 5. 변경 이력

- v0.1 (2026-10-13): 최초 작성. REQ-001(A~D), ADR-001~004, C-1~C-3.
