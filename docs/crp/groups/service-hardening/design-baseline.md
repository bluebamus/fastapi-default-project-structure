# Design Baseline — service-hardening (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.
>
> **ID 범위:** 이 문서의 `REQ-0xx`·`ADR-0xx`·`C-x` 는 **이 그룹 안에서만** 번호를 매긴다. 그룹 밖
> (코드 주석·README·다른 그룹 문서)에서 인용할 때는 반드시 `service-hardening ADR-0xx` 처럼 그룹
> 이름을 붙인다. 그룹 이름 없는 번호는 `orm-raw-repository` 그룹의 것이다.

## 0. 질의 수준 (Autonomy Level) — 이 그룹의 기획 질문 깊이

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-12 · 변경 이력: (없음)

> 안전 하한선: 어느 수준도 파괴적·외부영향·계약변경 STOP(WORKFLOW §4 ③④)은 못 건너뛴다.

## 1. 목적 / 배경

2026-10-07 전체 검수(로컬 보고서, 저장소 밖 도구 산출물이라 커밋하지 않는다)가 남긴 지적 중
**서비스로 띄우기 전에 막아야 하는 것**을 단계별로 고친다 — CI 재현성, DSN 조립, ORM 잠금 읽기·목록
정렬, 접속 로그 수집, 오류 매핑, 테스트 하네스, 시각 정책(UTC), Redis 필수화와 Celery 태스크 발견,
그리고 로그인 고도화(비밀번호 해시 이전·토큰 회전·레이트 리밋·인가·소유권). 모든 단계는 이 저장소가
이미 쓰는 방식(의존성 provider 함수 → 생성자 주입, 기능 디렉터리 자동 발견)을 따른다.

선행 그룹 `orm-raw-repository` 의 Active 요구·불가침 제약은 이 그룹에도 그대로 적용된다(§4 C-10).
그 그룹의 C-9("JWT 인증 정책과 Redis API client 는 범위 밖")만 이 요청으로 대체된다(ADR-002).

## 2. 요구사항 레지스터 (요청 히스토리 — append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-12 | "1,2,3,4,5,6,7,8 redis 필수, 9는 전통적인 방식과 fastapi에서 최신 사용하는 실무 코드를 기반으로, 일반적으로 개발되는 설계를 기반으로 작업 계획을 만들고 이를 기반으로 개발을 진행해줘. 각 단계는 단위 테스트가 반드시 진행되어야 한다. 모든 기능은 같은 목적의 기능이 하나의 모듈 클래스로 만들어져야 하고 필수 작업은 반드시 주입을 통해 조합, 데이터 전달, 인증 및 자동 작업 등이 진행되어야 하며…" | 단계 A~F2 를 순서대로 구현한다. 단계마다 단위 테스트(가능하면 fail-on-revert) + ruff·mypy·pytest(skip 0) 그린 후 커밋. 같은 목적의 기능은 한 클래스, 필수 협력 객체는 생성자 주입·provider 함수로 조립. 단계별 도출 요구는 아래 REQ-001-A~F2 | Active | ADR-001~020, C-1~C-10, charter §3, run-log Round 1~ |
| REQ-001-A | 2026-10-12 | (REQ-001 의 단계 A — 제안 1·2·3) | A1 CI 의 `uv sync` 가 락 불일치에서 실패한다(`--locked`). 게이트의 파일 목록은 git 이 추적하는 파일만. A2 DSN 은 `URL.create` 로 만들어 특수문자 비밀번호·IPv6 가 깨지지 않는다. A3 ORM 잠금 읽기는 writer 고정·read-only 거부, 범용 목록은 결정적 정렬(`created_at DESC, id DESC`) | Active | ADR-003~005, ledger F-001~F-005 |
| REQ-001-B | 2026-10-12 | (단계 B — 제안 4·5) | 신뢰 프록시 홉 수로만 클라이언트 IP 를 결정, 500 도 접속 로그에 기록, 쿼리스트링 민감 값 마스킹, 문자열은 모델 컬럼 길이로 절단, null PATCH 422, DB 오류 코드별 매핑, 리포트 날짜 범위 상한 | Active | ADR-006~008, ledger F-006~F-013 |
| REQ-001-C | 2026-10-12 | (단계 C — 제안 6) | 엔드포인트 테스트 공용 세션 헬퍼(read-only 표시 포함), MySQL ORM 스모크 | Active | ADR-009, ledger F-014~F-015 |
| REQ-001-D | 2026-10-12 | (단계 D — 제안 7) | DB 는 UTC·마이크로초 저장, 응답은 오프셋 포함 ISO 8601, 기존 데이터 변환 리비전, 리포트는 로컬 영업일 기준 유지 | Active | ADR-010, ledger F-016 |
| REQ-001-E | 2026-10-12 | (단계 E — 제안 8, "redis 필수") | Redis 는 API 필수 자원으로 유지하고 주입 provider 로 노출, `/ready` 가 DB·Redis 를 모두 본다, Celery 태스크는 기능별로 두고 자동 발견 | Active | ADR-011~012, ledger F-017~F-018 |
| REQ-001-F1 | 2026-10-12 | (단계 F1 — 제안 9 전반) | Argon2 해시(기존 bcrypt 점진 이전), JWT 표준 claim 검증, refresh 회전·재사용 탐지, 로그인·가입 레이트 리밋 | Active | ADR-013~016, ledger F-019~F-021 |
| REQ-001-F2 | 2026-10-12 | (단계 F2 — 제안 9 후반) | 토큰 기반 Principal 주입, 소유권 정책, 슈퍼유저 2단계 인가, 운영 도구(슈퍼유저 생성), SQLAdmin 정책 불변 | Active | ADR-017~020, ledger F-022~F-024 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-12 | 단계 순서는 A → B → C → D → E → F1 → F2. 단계(또는 단계 묶음)마다 피처 브랜치를 따고, 단계마다 단위 테스트 + fail-on-revert + ruff·mypy·`pytest -m "not mysql"`(skip 0) 를 통과한 뒤 커밋한다. MySQL·브라우저 마커 테스트는 작성만 하고 CI 가 실행한다. | 뒤 단계가 앞 단계에 기댄다 — 정렬(A3)·시각(D)이 C2 스모크의 전제이고, Redis provider(E1)가 F1 의 토큰 저장소·레이트 리밋의 전제다. | Accepted | — |
| ADR-002 | 2026-10-12 | `orm-raw-repository` 그룹의 **C-9**("JWT 인증 정책과 Redis API client 는 이번 범위 밖")를 이 그룹이 대체한다. JWT 인증 정책(F1·F2)과 Redis API client(E1)를 범위에 들인다. | C-9 는 그 그룹 착수 명세(requirements §4.5/§4.6, §17)의 **범위 한정**이었지 금지가 아니다. 2026-10-12 사용자 요청이 로그인 고도화(제안 9)와 "redis 필수"(제안 8)를 명시했다. 검수 보고서의 R-01·R-02·R-11·R-12·R-13 이 이 범위에 있고, R-13 의 질문("Redis 를 API 필수 의존으로 유지할 계획인가")에 대한 답이 이 결정이다. 원 그룹 문서에는 C-9 상태 줄만 덧붙인다(append-only). | Accepted | orm-raw-repository C-9 |
| ADR-003 | 2026-10-12 | CI 의 모든 `uv sync` 를 `--locked` 로 한다. `scripts/review_gate.py` 의 파일 목록은 `git ls-files -z` 로 만들고, git 을 쓸 수 없을 때만 `rglob` 으로 대체한다. | `--frozen` 은 락을 **검사하지 않고** 그대로 쓴다 — pyproject 를 고치고 락을 갱신하지 않아도 CI 가 초록이었고, 주석은 반대로 적혀 있었다. `--locked` 는 락이 pyproject 와 어긋나면 실패한다. 게이트가 작업 트리를 rglob 으로 훑으면 추적되지 않는 로컬 파일(다른 도구의 보고서 등)이 판정에 섞여 로컬과 CI 결과가 달라진다. | Accepted | — |
| ADR-004 | 2026-10-12 | DSN 은 `sqlalchemy.engine.URL.create()` 로 만든다. `MYSQL_URL`·`MYSQL_WRITER_URL`·`MYSQL_REPLICA_URLS`·`ALEMBIC_URL` 은 `URL` 객체를 돌려준다. 마스킹은 `render_as_string(hide_password=True)`. Alembic 은 `ALEMBIC_DATABASE_URL` 이 있으면 `make_url`, 없으면 writer URL 의 drivername 만 `mysql+pymysql` 로 바꾼다. `migrations/env.py` 는 `render_as_string(hide_password=False).replace("%", "%%")` 를 넘긴다(ConfigParser 보간). `REDIS_URL` 은 문자열을 유지하되 비밀번호를 `quote(pw, safe="")` 로 인코딩한다. | f-string 조립은 비밀번호의 `@ : / # % ?` 에서 파싱이 깨진다(검수 R-10). 운영 비밀번호에서만 드러나는 실패라 테스트 기본값으로는 보이지 않는다. 엔진은 `URL` 을 그대로 받으므로 문자열로 되돌릴 이유가 없다. 자체 `mask_dsn` 은 `URL` 이 같은 일을 하므로 지운다. | Accepted | — |
| ADR-005 | 2026-10-12 | ① `Select` 의 `_for_update_arg` 가 있으면(ORM `with_for_update()`) 라우팅은 쓰기(writer 고정), read-only 세션은 거부한다. ② `BaseRepository.list()` 의 기본 정렬은 `created_at DESC, <PK> DESC`(created_at 이 없으면 PK 만). 공개 메서드 8개는 늘리지 않는다. ③ `created_at desc` 단일 키 쿼리에 `id desc` 보조 키를 붙인다. | ① text SQL 의 `FOR UPDATE` 는 이미 막는데 ORM 잠금 읽기는 replica 로 가고 read-only 도 통과했다(검수 R-14) — 같은 개념이 경로에 따라 달랐다. ② ORDER BY 없는 offset 페이지는 MySQL 에서 비결정적이라 페이지가 겹치거나 빠진다. ③ 같은 시각(초 단위 저장 시 흔하다)의 행 순서가 실행마다 달라진다. | Accepted | — |
| ADR-006 | 2026-10-12 | 클라이언트 IP 는 core 의 모듈 클래스 `ClientIPResolver` 가 정한다. 설정 `TRUSTED_PROXY_HOPS`(기본 0): 0 이면 직접 피어, N 이면 `X-Forwarded-For` 목록 + 직접 피어에서 **오른쪽 N번째**. 결과는 `ipaddress` 로 검증하고 실패하면 직접 피어. `X-Real-IP` 는 hops>0 이고 XFF 가 없을 때만. | XFF 를 무조건 믿으면 헤더 한 줄로 감사 로그의 IP 를 위조한다(검수 R-08). 홉 수 방식은 uvicorn `--forwarded-allow-ips` 와 같은 모델이고 설정 하나로 운영 토폴로지를 표현한다. | Accepted | — |
| ADR-007 | 2026-10-12 | 접속 로그 미들웨어는 `call_next` 예외를 status 500 으로 기록한 뒤 다시 던진다. 쿼리스트링의 민감 키(설정 `ACCESS_LOG_SENSITIVE_QUERY_KEYS`) 값은 `***` 로 저장한다. 문자열 길이는 저장 직전 home 기능이 **모델 컬럼 길이**(`Model.__table__.c[name].type.length`)로 자른다 — 숫자를 두 번 적지 않는다. | 500 요청이 로그에서 빠졌다(R-09). 쿼리스트링에 토큰·비밀번호가 실린 요청이 그대로 저장됐다(R-02 일부). MySQL strict 모드에서 길이 초과 INSERT 가 실패하고 조용히 버려져 감사 로그를 회피할 수 있었다(R-08). core 는 모델을 모르므로 절단은 기능 쪽이 한다. | Accepted | — |
| ADR-008 | 2026-10-12 | ① 모든 Update 스키마는 공통 기반 `PatchSchema` 를 상속하고, 보낸 필드 중 값이 None 인데 nullable 로 선언되지 않은 필드는 422. ② DB 오류 변환을 한 곳에 모아 코드별로 나눈다: 중복 → 409, NOT NULL → 422, 참조 대상 없음(1452) → 422, 참조 중(1451) → 409, 그 외 500. 메시지에 원문·SQL 을 싣지 않는 규칙은 유지. ③ 리포트 날짜 범위에 상한(최대 366일, 1970-01-01..9998-12-31). ④ status<500 예외 로그는 WARNING. | ① null 이 NOT NULL 컬럼으로 내려가 500 이 났다. ② 모든 IntegrityError 를 409 DUPLICATE 로 보내 원인이 가려졌다(검수 Low 항목). ③ 날짜 연산 overflow·과대 스캔. ④ 4xx 가 ERROR 로 쌓여 경보를 흐렸다. | Accepted | — |
| ADR-009 | 2026-10-12 | 엔드포인트 테스트의 세션 override 는 공용 헬퍼 하나로 만든다 — writer override 는 `using_writer`, read-only override 는 `mark_read_only` 를 거친 세션. MySQL ORM 스모크(`mysql` 마커)로 CRUD·정렬 안정성·collation·null PATCH·길이 절단을 실제 MySQL 에서 확인한다. | read-only override 가 표시 없는 일반 세션이라 GET 경로의 실수 쓰기가 테스트를 통과했다(R-15). MySQL 통합 테스트가 Raw SQL·마이그레이션 8건뿐이었다(R-16). | Accepted | — |
| ADR-010 | 2026-10-12 | DB 시각은 UTC·마이크로초로 저장하고 응답은 오프셋 포함 ISO 8601. core 에 `UTCDateTime` TypeDecorator(impl `DateTime()` + MySQL `DATETIME(fsp=6)`; bind 는 aware→UTC 후 tzinfo 제거, naive 는 `ValueError`; result 는 UTC 부착). 시각 생성은 한 곳(`utc_now`). Alembic 리비전이 기존 값을 `CONVERT_TZ(col,'+09:00','+00:00')` 로 옮긴다(Asia/Seoul 은 DST 없음). 리포트는 설정 TIME_ZONE 의 **고정 오프셋**으로 로컬 영업일 집계를 유지. Celery `enable_utc=True`. | KST 벽시계가 오프셋 없이 `DATETIME(0)` 에 저장돼 스키마 설명 "(UTC)" 와 어긋났고 소수 초 반올림이 자정 경계 집계를 바꿨다(검수 R-05). naive 값을 조용히 받아들이면 같은 오해가 다시 생긴다. 고정 오프셋의 한계는 residual-risk R-003. | Accepted | — |
| ADR-011 | 2026-10-12 | **Redis 는 API 필수 자원으로 유지한다.** lifespan 이 클라이언트를 소유하고(기존), 주입 provider `get_redis(request)` 하나로 노출한다(core). `/ready` 는 DB 와 Redis 를 각각 2초 안에 ping 하고 하나라도 실패하면 503(응답에 원문 없음). | 사용자 결정 "redis 필수"(REQ-001). refresh 토큰 저장소·레이트 리밋(F1)이 Redis 를 쓰므로 검수 R-13("API 는 쓰지 않는 Redis 가 기동 조건")의 전제가 사라진다. 장애 시 fail-closed 는 residual-risk R-005. | Accepted | — |
| ADR-012 | 2026-10-12 | Celery 태스크는 기능별 `tasks.py` 로 옮기고, 워커의 include 는 **이 저장소의 기능 패키지 자동 발견**(`app/core/db/models_registry.py` 가 모델을 찾는 것과 같은 방식 — `app/features/*` 탐색)으로 만든다. 중앙 파일이 기능을 import 하지 않는다. 워커 기동 시 모델 등록도 같은 경로. 태스크 본문의 서비스 조립은 그 기능의 provider 함수(세션을 인자로 받는 일반 함수)를 재사용한다. | 중앙 `app/celery/tasks.py` 가 모든 기능을 알아 기능을 지우면 워커가 깨졌다. 모델 발견과 같은 메커니즘을 쓰면 규칙이 하나다. | Accepted | — |
| ADR-013 | 2026-10-12 | 비밀번호 해시는 인증 기능 소유의 모듈 클래스 `PasswordHasher` — `pwdlib[argon2]`(Argon2id). 검증은 `verify_and_update` 의미: 기존 bcrypt 해시(`$2` 접두사)는 기존 규칙(72바이트 절단)으로 검증하고 성공하면 새 Argon2 해시를 돌려줘 로그인 시 재해시 저장(점진 이전). 타이밍 균등화 더미 해시도 Argon2. 의존성 `pwdlib[argon2]` 추가, dev 에 `fakeredis` 추가(`uv add`). | FastAPI 공식 문서의 현행 권장이 pwdlib + Argon2 다. 전체 재해시는 평문이 없어 불가능하므로 로그인 시 이전이 유일한 무중단 경로다. bcrypt 의 72바이트 조용한 절단(검수 Low)도 새 해시에서 사라진다. fakeredis 는 Redis 를 쓰는 실물 클래스를 그대로 시험하기 위해서다(가짜 Protocol 을 만들지 않는다). | Accepted | — |
| ADR-014 | 2026-10-12 | 토큰은 core security 의 `TokenService`(PyJWT)가 발급·검증한다. claims `sub, type, iat, nbf, exp, jti, iss, aud` + access 는 `username`·`su`, refresh 는 `fam`. decode 는 `algorithms=[설정]`·`audience`·`issuer`·`options={"require": [...]}`·`leeway`. 설정 `JWT_ISSUER`·`JWT_AUDIENCE`·`JWT_LEEWAY_SECONDS`, `JWT_ALGORITHM` 은 `Literal["HS256","HS384","HS512"]`, `ACCESS_TOKEN_EXPIRE_MINUTES` 기본 15. | 발급은 auth 기능이, 검증은 core 의존성(Principal)이 쓰므로 core 에 둔다. iss/aud/type 검증이 없으면 refresh 토큰을 access 로 쓰는 혼동·다른 서비스 토큰 재사용이 통과한다. 짧은 access 만료가 즉시 폐기의 대안이다(residual-risk R-002). | Accepted | — |
| ADR-015 | 2026-10-12 | refresh 회전은 core security 의 `RefreshTokenStore`(Redis): 발급 시 `auth:rt:{jti}` → `{fam, sub}`(TTL=refresh 만료)와 `auth:user:{sub}:fams` 집합. 회전 시 `GETDEL` 로 jti 를 소비하고, 없으면 **재사용 탐지** → family 폐기(`auth:fam:{fam}:revoked`) → 401. `revoke_family`, `revoke_user`(비활성화·삭제 시). | 탈취된 refresh 로 7일간 재발급이 가능했다(검수 R-11). 회전 + 재사용 탐지는 OAuth 2.0 Security BCP 의 권장 방식이다. GETDEL 하나가 원자적이라 경쟁 시 한쪽만 성공한다 — Lua 스크립트가 필요 없다. | Accepted | — |
| ADR-016 | 2026-10-12 | 레이트 리밋은 core security 의 `RateLimiter`(Redis 고정 창, `INCR` + 첫 hit 에 `EXPIRE`). 설정 `AUTH_LOGIN_RATE_LIMIT`(ip+username), `AUTH_LOGIN_IP_RATE_LIMIT`(ip), `AUTH_REGISTER_RATE_LIMIT`(ip). 로그인 성공 시 ip+username 카운터 삭제. 초과는 `TooManyRequestsException`(429, `Retry-After`). 핸들러 본문이 아니라 라우트 의존성(`Depends`)으로 건다. | 로그인 시도 제한이 없었다(검수 R-12). 고정 창은 구현이 가장 단순하고 Redis 명령 두 개로 끝난다 — 창 경계 버스트(최대 2배)는 residual-risk R-004 로 수용. | Accepted | — |
| ADR-017 | 2026-10-12 | 인증 주체는 core security 의 `Principal`(id, username, is_superuser) — access 토큰만으로 만든다(DB 조회 없음). 의존성 `get_current_principal`(OAuth2 Bearer → `TokenService`), `require_superuser`, 별칭 `CurrentPrincipal`. 인증 성공 시 `request.state.user_id` 를 채운다. DB 의 사용자 엔티티가 필요한 곳(`/me`)만 `get_current_user` 를 쓴다. | 기능끼리 import 하지 않는 계층 규칙(C-2)을 지키면서 모든 기능이 인증을 쓰려면 의존 대상이 core 하나여야 한다. 상태 없는 검증이라 요청마다 DB 왕복이 없다. 접속 로그의 `user_id` 가 이제 채워진다. | Accepted | — |
| ADR-018 | 2026-10-12 | 인가는 **슈퍼유저/일반 2단계**. `users.is_superuser`(기본 False) 와 blog·sns·reply 의 `author_id`(nullable, index)를 Alembic 리비전으로 추가. 소유권은 core security 의 한 클래스 `OwnershipPolicy.ensure_can_modify(owner_id, principal)` — 소유자 또는 슈퍼유저, 아니면 403. 서비스 메서드가 principal 을 인자로 받아 호출한다. 기존 행의 `author_id` 는 NULL(슈퍼유저만 수정). | 무인증 CRUD 로 남의 계정을 잠그거나 지울 수 있었다(검수 R-01), 접속 로그 API 가 PII 를 공개했다(R-02). RBAC 세분화는 비목표 — 2단계로 템플릿의 공백(인증 적용 예시 0건)을 메운다. | Accepted | — |
| ADR-019 | 2026-10-12 | **SQLAdmin 정책은 바꾸지 않는다** — `orm-raw-repository` C-8(기본값 true·인증 백엔드 없음·배포 환경 확인 플래그)을 그대로 유지하고 이 그룹의 범위 밖으로 명시한다. | 사용자 결정으로 확정된 기존 정책이고(그 그룹 ADR-045), 관리자 인증 백엔드는 이번 요청에 없다. 위험은 residual-risk R-001 로 남긴다. | Accepted | — |
| ADR-020 | 2026-10-12 | 운영 도구 `scripts/create_superuser.py`(Django `createsuperuser` 와 같은 역할): 인자/환경변수/getpass 로 입력, 서비스·리포지토리를 background 세션으로 조립(주입 경로 재사용), 이미 있으면 승격. `/users` POST 는 비밀번호 필수(로그인 불가 계정 금지). | 슈퍼유저가 생기면 첫 슈퍼유저를 만드는 경로가 필요하다. API 로 열면 부트스트랩 문제가 생기므로 서버 밖 도구로 둔다. | Accepted | — |

## 4. 불가침 제약 (INVARIANT REQUIREMENTS — 추가 작업이 위반 금지)

- **C-1**: 필수 협력 객체(저장소·해시·토큰·Redis·레이트 리밋·정책)는 생성자 인자로 받고, 조립은 기능의 `dependencies/*_dependencies.py` provider 함수(`Depends`)가 한다. 구현이 하나뿐인 Protocol·팩토리는 만들지 않는다. 테스트는 `app.dependency_overrides` 나 생성자 인자(fakeredis 포함)로 바꾼다. (REQ-001)
- **C-2**: 계층 규칙 — 기능끼리 import 금지(문서화된 auth→user 예외만), core→features 금지, utils→core 금지. 기능 간 공유가 필요하면 core 로 올린다.
- **C-3**: 커밋은 쓰기 핸들러가 응답 DTO 검증 후 정확히 1회. 의존성 함수·Repository 는 commit 하지 않는다(`orm-raw-repository` C-2 계승).
- **C-4**: 각 단계는 새 동작마다 단위 테스트를 두고, ruff check·ruff format·mypy·`pytest -m "not mysql"`(skipped/xfailed 0)가 그린이어야 커밋한다. (REQ-001 "각 단계는 단위 테스트가 반드시")
- **C-5**: (단계 D 이후) DB 에 저장하는 시각은 UTC 다. naive datetime 은 저장 경로에서 거부한다.
- **C-6**: Redis 는 API 필수 자원이다 — 끄는 설정을 두지 않는다. (ADR-011)
- **C-7**: 인증·인가는 주입 경로(`Depends`)로만 한다. 핸들러 본문이 토큰을 직접 파싱하지 않는다.
- **C-8**: 비밀번호·토큰·DSN 비밀번호를 로그·오류 응답에 싣지 않는다.
- **C-9**: SQLAdmin 정책은 바꾸지 않는다(ADR-019).
- **C-10**: `orm-raw-repository` 그룹의 Active 불가침 제약(C-1~C-8)을 계승한다. 단, 그 그룹 C-1(공개 API 불변)은 F2 의 **의도된** 변경(인증 요구·403/401 추가)에 한해 OpenAPI 기준선을 갱신하고 그 이유를 이 그룹 run-log 에 적는다.

## 5. 변경 이력

- v0.1 (2026-10-12): 최초 작성. REQ-001(단계 A~F2 도출 요구 포함), ADR-001~020, C-1~C-10 등록. `orm-raw-repository` C-9 를 ADR-002 로 대체.

---
> **연동:** charter 의 계약/불변식은 이 문서의 Active 요구사항·불가침 제약과 **모순되면 안 된다**
> (모순 시 design-baseline 이 우선 — charter 를 고친다). run-log 는 라운드별로 어떤 Req/ADR 를
> 충족·참조했는지 적는다.
