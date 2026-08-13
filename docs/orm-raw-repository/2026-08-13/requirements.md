# ORM/Raw Repository 고도화 요구 명세서

## 1. 문서 정보

| 항목 | 값 |
|---|---|
| 문서 목적 | ORM 및 Raw SQL 데이터 접근 방식의 구조·동작·품질 요구사항 정의 |
| 적용 프로젝트 | `fastapi-default-project-structure` |
| 기준 구조 | 현재 `main.py` 명시 라우터 취합 및 Dependency → Service → Repository 흐름 |
| 관련 계획서 | `docs/orm-raw-repository/2026-08-13/development-plan.md` |
| 관련 지침서 | `docs/orm-raw-repository/2026-08-13/workflow-guide.md` |
| 상태 | 개발 착수 전 요구사항 기준선 |

## 2. 목표

본 작업은 현재 프로젝트의 FastAPI 워크플로우를 유지하면서 다음 두 데이터 접근 방식을
일관된 구조로 제공해야 한다.

1. SQLAlchemy ORM 모델 기반 CRUD 및 도메인 조회
2. SQLAlchemy `text()` 기반 Raw SQL 조회 및 변경

두 방식은 Repository 구현만 달라야 하며 다음 항목은 동일해야 한다.

- Dependency Injection과 객체 조립
- Service 유스케이스 실행
- read-only/writer DB session 선택
- 트랜잭션 경계
- Pydantic 입력·응답 검증
- 버전별 라우터 구성과 `main.py` 최종 취합
- OpenAPI/Scalar 문서 품질
- 예외 처리, 테스트 및 정적 검사 기준

## 3. 용어

| 용어 | 정의 |
|---|---|
| View | FastAPI path operation 함수. HTTP 계약과 유스케이스 호출을 담당한다. |
| Dependency | FastAPI `Depends`로 세션과 Service를 생성·조립하는 함수다. |
| Service | 비즈니스 규칙과 유스케이스 순서를 담당한다. |
| Repository | ORM 또는 Raw SQL 데이터 접근을 담당한다. |
| ORM Base | `CRUDBase`와 이를 상속하는 `BaseRepository` 계층이다. |
| Raw Base | `RawCRUDBase`와 이를 상속하는 `RawRepositoryBase` 계층이다. |
| DTO | 외부 요청·응답 계약을 표현하는 Pydantic 모델이다. |
| 쓰기 View | DB 상태를 변경하는 POST/PUT/PATCH/DELETE path operation이다. |
| 조회 View | DB 상태를 변경하지 않는 GET/HEAD path operation이다. |

## 4. 요구사항 해석 및 보강 결정

### 4.1 View에서 비즈니스 코드 실행

원 요구사항의 “비즈니스 코드는 View에서 실행한다”는 다음 의미로 확정한다.

> View는 Dependency로 주입받은 Service의 비즈니스 유스케이스를 호출하여 실행한다.
> 비즈니스 규칙 자체는 Service에 작성하고 SQL은 Repository에 작성한다.

View에 직접 작성할 수 있는 코드는 다음으로 제한한다.

- HTTP 파라미터와 요청 본문 수신
- Service 유스케이스 호출
- 쓰기 성공 후 응답 전 commit 호출
- 반환값의 Pydantic 응답 변환
- HTTP 상태와 OpenAPI 메타데이터 선언

### 4.2 공통 모델 상속

모든 ORM 모델은 `Base` 계층을 사용해야 하지만 모든 테이블에 동일한 컬럼을 강제하지
않는다. 공통 필드는 작은 mixin으로 조합한다.

- 일반 변경 가능 엔티티: UUID PK + created/updated timestamp
- 생성 후 불변 로그: UUID PK + created timestamp
- 외부 시스템 PK 사용 테이블: 해당 PK 정책을 명시적으로 예외 처리

### 4.3 Scalar 문서의 계약 출처

ORM 모델은 DB 매핑 계약이며 Scalar API 문서의 직접 계약이 아니다. Scalar 문서는
FastAPI View와 Pydantic DTO가 생성한 OpenAPI schema를 기준으로 한다.

- ORM 응답: ORM 객체 → `from_attributes=True` Pydantic 응답 DTO
- Raw 응답: `RowMapping` → 명시적 `dict` 변환 → Pydantic 응답 DTO
- ORM 컬럼 comment는 Pydantic 설명을 대체하지 않는다.

### 4.4 Raw SQL 사용 원칙

Raw SQL은 ORM을 우회하기 위한 일반 기본값이 아니다. 다음 상황에서 선택한다.

- 복잡한 집계, 윈도 함수, CTE 또는 DB 최적화 쿼리
- ORM 표현보다 SQL 계약이 더 명확한 리포트
- 실행 계획을 기준으로 관리해야 하는 성능 민감 조회
- 기존 DB의 저장 프로시저 또는 DB 전용 기능 연계

일반 단일 테이블 CRUD는 ORM Repository를 우선한다.

### 4.5 JWT 인증 적용 범위

프로젝트의 기본 인증 방식은 JWT를 전제로 하지만 이번 ORM/Raw Repository 및 lifecycle
고도화 작업에는 JWT 인증 기능의 신규 적용이나 확장을 포함하지 않는다. 현재 인증 동작은
호환성 기준선으로만 보호한다.

Access/refresh token 정책, rotation, revoke/logout, 권한 모델과 보안 저장 방식은 별도의
후속 요구 명세에서 정의한다.

### 4.6 Redis 적용 범위

API용 Redis client, cache, session 저장소와 readiness 연계는 이번 작업에 포함하지 않고 JWT와
마찬가지로 후속 요구 명세로 분리한다. 기존 Celery broker/backend의 Redis 설정과 동작은
변경하지 않는다.

## 5. 우선순위

| 등급 | 의미 |
|---|---|
| P0 | 구현 및 배포 전에 반드시 충족해야 하는 구조·보안·정합 요구사항 |
| P1 | 이번 고도화 범위에서 반드시 제공해야 하는 기능·테스트 요구사항 |
| P2 | 호환성을 유지하면서 점진적으로 적용할 품질 개선 요구사항 |

## 6. 아키텍처 요구사항

### AR-001 공통 계층 흐름 [P0]

ORM과 Raw View는 모두 다음 호출 흐름을 준수해야 한다.

```text
View -> Dependency -> Service -> Repository -> AsyncSession
```

수용 기준:

- View가 `AsyncSession`을 직접 주입받지 않는다.
- View와 Service가 `session.execute()`를 직접 호출하지 않는다.
- Repository가 FastAPI `Request`, `Response`, `Depends`를 import하지 않는다.

### AR-002 공통 모듈 위치 [P0]

모든 기능에서 재사용하는 DB, middleware, model base, repository base, service base와 태그
메타데이터는 `app/core` 아래에 둬야 한다.

수용 기준:

- 기능 간 상대 기능 import로 공통 코드를 공유하지 않는다.
- 도메인 SQL과 도메인 규칙을 `app/core`에 두지 않는다.

### AR-003 ORM/Raw Base 분리 [P0]

ORM Base와 Raw Base는 각각 독립적인 상속 계층이어야 한다.

```text
BaseRepository -> CRUDBase
RawRepositoryBase -> RawCRUDBase
```

수용 기준:

- `RawRepositoryBase`가 `BaseRepository`를 상속하지 않는다.
- 하나의 Base 클래스가 ORM 모델과 Raw row를 동시에 반환하지 않는다.
- 공유되는 것은 `AsyncSession`, 공통 예외와 로깅 정책뿐이다.

### AR-004 명시적 라우터 취합 [P0]

라우터는 자동 발견하지 않고 다음 순서로 명시 취합해야 한다.

```text
v1/<view>.py -> api/routers/router.py -> feature/__init__.py -> main.py
```

수용 기준:

- 각 기능 패키지는 `router`를 공개한다.
- `main.py`가 `app.include_router(feature.router, prefix="/api")`로 최종 등록한다.
- 새 기능의 라우터 등록 누락을 테스트가 탐지한다.

### AR-005 Lifespan Resource Manager [P0]

애플리케이션 프로세스 수명 자원의 생성과 해제는
`app/core/resources.py`의 `manage_application_resources(app)` 한 곳에서 관리해야 한다.

수용 기준:

- `main.py`의 lifespan은 resource manager context를 호출하고 yield하는 조립만 담당한다.
- startup과 shutdown 로직이 기능 모듈 또는 여러 event handler에 분산되지 않는다.
- 실제 생성된 자원을 `app.state.resources`에서 명시적으로 참조할 수 있다.
- cleanup 완료 후 `app.state.resources`가 닫힌 자원을 참조하지 않는다.
- 범용 자동 registry나 decorator framework 없이 명시적 순서를 유지한다.

### AR-006 자원 소유권 [P0]

Resource Manager는 FastAPI API 프로세스가 생성하고 소유한 장기 수명 자원만 관리해야 한다.

수용 기준:

- DB writer, reader, background engine pool을 shutdown에서 dispose한다.
- DB engine 정의가 session 모듈에 남더라도 shutdown 소유자는 Resource Manager 하나다.
- 요청별 `AsyncSession`은 Dependency가 닫는다.
- Celery worker의 broker/backend 연결을 FastAPI lifespan이 닫지 않는다.
- shutdown에서 DB table drop을 실행하지 않는다.

### AR-007 모델 기반 테이블 생성 조건 [P0]

startup은 모든 모델 모듈을 import한 후 `Base.metadata.tables`의 실제 테이블 수를 기준으로
테이블 자동 생성 여부를 결정해야 한다.

수용 기준:

- metadata table 수가 0이면 DB 연결과 `create_all()`을 시도하지 않는다.
- metadata table 수가 1 이상이고 개발 자동 생성 정책이 활성화된 경우만 생성한다.
- 운영 환경에서는 모델이 있어도 `create_all()`을 실행하지 않고 Alembic을 사용한다.
- 모델 파일 존재 여부만으로 생성 여부를 판정하지 않는다.
- 동일 startup에서 모델 discovery/import를 중복 실행하지 않는다.

### AR-008 실패 안전 cleanup [P0]

정상 shutdown뿐 아니라 startup 중간 실패에서도 이미 생성된 자원을 정리해야 한다.

수용 기준:

- startup 전체가 `try/finally` 또는 동등한 async context manager cleanup으로 보호된다.
- 하나의 cleanup 실패 때문에 다른 자원 cleanup이 생략되지 않는다.
- 종료 순서는 background task drain, DB engine dispose, logging queue flush/listener stop이다.
- 자원별 shutdown timeout이 존재한다.

### AR-009 Background task 완전 종료 [P0]

`BackgroundTaskRunner`는 shutdown timeout 후에도 task를 실행 상태로 남겨서는 안 된다.

수용 기준:

- timeout 전 완료된 task 결과를 회수한다.
- timeout 후 pending task에 `cancel()`을 호출한다.
- 취소한 task를 `asyncio.gather(..., return_exceptions=True)` 또는 동등한 방식으로 await한다.
- cancellation이 session context의 rollback/close를 실행할 기회를 보장한다.
- drain 완료 후 추적 task 집합이 비어 있다.
- 모든 task 종료 후 DB를 dispose하고 logging listener를 마지막에 닫는다.

### AR-010 Celery worker async 자원 종료 [P0]

Celery worker process가 소유한 영속 event loop와 DB pool은 worker shutdown signal에서
명시적으로 종료해야 한다.

수용 기준:

- Celery 동기 task wrapper 내부의 DB 호출은 기존 async Service/Repository를 사용한다.
- worker process별 event loop를 재사용한다.
- worker shutdown에서 DB engine/pool을 loop가 살아 있는 동안 dispose한다.
- `shutdown_asyncgens()` 실행 후 event loop를 close한다.
- 종료 후 global loop reference를 `None`으로 초기화한다.
- FastAPI lifespan과 Celery worker cleanup의 소유권이 섞이지 않는다.

## 7. ORM 모델 요구사항

### ORM-MDL-001 공통 Declarative Base [P0]

모든 ORM 모델은 `app/core/models/models_base.py`에서 정의한 `Base` 계층을 사용해야 한다.

수용 기준:

- 독립적인 `DeclarativeBase`가 기능 폴더에 존재하지 않는다.
- 모든 모델이 Alembic과 `Base.metadata`에 등록된다.

### ORM-MDL-002 공통 필드 mixin [P1]

UUID와 timestamp를 반복 선언하지 않고 공통 mixin을 사용해야 한다.

수용 기준:

- `UUIDPrimaryKeyMixin`, `CreatedAtMixin`, `UpdatedAtMixin`으로 책임을 분리한다.
- 변경 가능 엔티티는 세 Mixin 조합을, 불변 로그는 UUID와 created 조합만 사용한다.
- 기존 모델 전환 후 Alembic schema diff가 발생하지 않는다.
- 불변 로그 모델은 불필요한 `updated_at`을 강제받지 않는다.

### ORM-MDL-003 PK 타입 계약 [P1]

ORM Repository의 PK 타입 가정을 제네릭 계약으로 표현해야 한다.

수용 기준:

- `BaseRepository[ModelT, PrimaryKeyT]`를 정식 타입 계약으로 사용한다.
- 기존 문자열 UUID Repository는 `BaseRepository[ModelT, str]`로 명시한다.
- Base가 문자열 `id`를 암묵적으로 가정하지 않는다.
- 외부 PK 모델의 예외 정책이 문서와 테스트에 명시된다.

### ORM-MDL-004 컬럼 계약 [P1]

모델은 DB 제약과 Python 타입을 일치시켜야 한다.

수용 기준:

- nullability, unique, index, FK와 `Mapped` 타입이 모순되지 않는다.
- DB에서 의미가 있는 컬럼에는 필요에 따라 comment를 제공한다.
- API 필드 설명은 Pydantic DTO에 별도로 정의한다.

## 8. ORM Repository 요구사항

### ORM-REP-001 CRUD primitive 책임 [P0]

`crud_base.py`는 ORM 영속성 primitive만 제공해야 한다.

필수 책임:

- session 저장
- PK 조회
- entity add/delete
- flush/refresh

금지 책임:

- commit/rollback
- HTTP 예외 생성
- eager loading과 도메인 전용 쿼리

### ORM-REP-002 안정적인 공개 CRUD [P1]

`repository_base.py`는 일반 모델에서 반복되는 최소 공개 CRUD를 제공해야 한다.

필수 API:

- create
- get by ID 및 not-found 변형
- pagination list
- count와 exists
- update by ID
- delete by ID

이 목록이 Base의 최소 정식 공개 API다. 기존 이름은 호환 wrapper로만 유지한다.

수용 기준:

- 공개 메서드 이름과 반환 타입이 타입 검사된다.
- 모든 ORM 기능 Repository가 이 Base를 상속한다.
- 기존 API 응답과 상태 코드가 유지된다.

### ORM-REP-003 입력 불변성 [P0]

Repository는 호출자가 전달한 `dict`를 변경해서는 안 된다.

수용 기준:

- create/bulk create/update 호출 후 원본 입력과 호출 전 값이 동일하다.
- ID 기본값은 모델 default 또는 복사된 데이터에서 처리한다.
- 입력 불변성 테스트가 존재한다.

### ORM-REP-004 존재 확인 최적화 [P2]

존재 확인은 전체 row count보다 SQL `EXISTS`를 사용해야 한다.

수용 기준:

- `exists`, `exists_by`가 boolean 존재 확인 SQL을 생성한다.
- 반환 타입은 항상 `bool`이다.

### ORM-REP-005 고급 쿼리 분리 [P1]

eager loading, join, partial column, batch와 같은 고급 쿼리는 실제 공통성이 확인된 경우만
Base에 둬야 한다.

수용 기준:

- 도메인 특화 관계명과 컬럼명이 Base에 없다.
- 문자열 관계·컬럼 접근을 신규 public API에서 확대하지 않는다.
- 기능별 쿼리는 해당 기능 Repository의 명시적 메서드가 소유한다.
- 두 개 이상의 실제 기능에서 같은 구현이 확인된 경우에만 별도 Mixin으로 추출한다.

### ORM-REP-006 예외 변환 일관성 [P0]

모든 create/update/delete/bulk 경로는 동일한 DB 예외 변환 정책을 사용해야 한다.

수용 기준:

- 무결성 충돌은 프로젝트 중복 또는 DB 예외로 변환된다.
- 예상하지 못한 SQLAlchemy 오류는 `DatabaseException`으로 변환된다.
- 원본 예외가 exception chaining으로 보존된다.
- 민감한 SQL 파라미터를 사용자 응답에 포함하지 않는다.

### ORM-REP-007 점진적 호환성 [P1]

기존 `BaseRepository` public 메서드는 사용처 조사 없이 즉시 삭제하지 않는다.

수용 기준:

- 메서드별 사용처 목록이 작성된다.
- 호환 wrapper → 호출부 전환 → 제거 순서로 변경한다.
- 전환 중 기존 201개 기준 테스트와 API contract가 유지된다.

## 9. Raw Repository 요구사항

### RAW-REP-001 RawCRUDBase 제공 [P0]

`app/core/repositories/raw_crud_base.py`를 추가해야 한다.

필수 protected API:

- `_fetch_one(TextClause, params) -> RowMapping | None`
- `_fetch_all(TextClause, params) -> Sequence[RowMapping]`
- `_fetch_scalar(TextClause, params) -> object`
- `_execute(TextClause, params) -> int`

수용 기준:

- 문자열 SQL보다 `TextClause` 입력을 기본 계약으로 사용한다.
- 결과 형태별 테스트가 존재한다.
- commit/rollback을 수행하지 않는다.

### RAW-REP-002 RawRepositoryBase 제공 [P0]

`app/core/repositories/raw_repository_base.py`를 추가해야 한다.

필수 책임:

- RawCRUDBase primitive의 안정적인 public API 제공
- SQLAlchemy 예외의 프로젝트 예외 변환
- keyword-only `query_name`을 받는 쿼리 이름 중심 로깅
- 민감 파라미터 미노출

수용 기준:

- 기능 Raw Repository가 이 Base를 상속한다.
- 도메인 SQL은 Base가 아닌 기능 Repository에 존재한다.
- 기능 Repository가 `feature.use_case` 형식의 안정적인 `query_name` 상수를 전달한다.
- Base는 `query_name`, 소요 시간과 성공/실패만 기록하고 SQL 본문과 params를 기록하지 않는다.

### RAW-REP-003 named parameter 강제 [P0]

모든 외부 값은 named bind parameter로 전달해야 한다.

허용 예:

```python
text("SELECT * FROM orders WHERE user_id = :user_id")
```

금지 예:

```python
text(f"SELECT * FROM orders WHERE user_id = '{user_id}'")
```

수용 기준:

- 사용자 입력을 SQL 문자열에 직접 보간한 코드가 없다.
- 보안 테스트 또는 정적 검사로 대표 injection 입력을 검증한다.

### RAW-REP-004 식별자 allowlist [P0]

테이블명, 컬럼명, 정렬 방향처럼 bind parameter를 사용할 수 없는 식별자는 코드가 소유한
allowlist에서 선택해야 한다.

수용 기준:

- 요청값이 SQL 식별자로 직접 사용되지 않는다.
- 허용하지 않은 정렬 키와 방향은 validation error가 된다.

### RAW-REP-005 결과 타입 및 DTO 경계 [P0]

Raw Repository는 `RowMapping` 또는 scalar를 반환하고 Service가 Pydantic DTO로 검증해야
한다.

수용 기준:

- View가 `Row`, `RowMapping`, `CursorResult`를 직접 반환하지 않는다.
- Raw 결과 컬럼 alias와 DTO 필드가 일치한다.
- 누락 또는 잘못된 타입의 결과가 Pydantic 검증에서 탐지된다.

### RAW-REP-006 DB 방언 관리 [P1]

MySQL 전용 SQL은 명시적으로 관리하고 해당 DB에서 통합 검증해야 한다.

수용 기준:

- MySQL 전용 함수와 문법에 주석 또는 문서 표시가 있다.
- SQLite 테스트 통과만으로 MySQL SQL의 정확성을 승인하지 않는다.
- 최소 한 개의 MySQL 통합 테스트 또는 실행 계획 검증 절차가 있다.
- 로컬과 CI가 동일한 `compose.test.yaml` MySQL service 구성을 사용한다.

### RAW-REP-007 Raw DML 지원 [P1]

Raw update/delete/insert를 사용할 때도 ORM과 같은 트랜잭션 규칙을 적용해야 한다.

수용 기준:

- Raw Repository는 affected row count만 반환하고 commit하지 않는다.
- 쓰기 View가 응답 전에 한 번 commit한다.
- read-only session에서 Raw DML이 차단된다.

## 10. Dependency 및 트랜잭션 요구사항

### TX-001 Dependency 조립 책임 [P0]

Dependency는 세션을 선택하고 Service와 Repository 객체를 조립해야 한다.

수용 기준:

- Dependency가 Service 유스케이스를 실행하지 않는다.
- Dependency가 commit하지 않는다.
- teardown commit 패턴을 사용하지 않는다.

### TX-002 조회 세션 [P0]

조회 View는 `get_read_only_db_session` 기반 read-only Service Dependency를 사용해야 한다.

수용 기준:

- GET/HEAD 경로가 `get_writer_db_session` 또는 `get_routed_db_session`을 사용하지 않는다.
  단, 강한 일관성이 필요한 승인된 예외는 사유와 함께 allowlist로 관리한다.
- 조회 경로의 commit 호출 횟수는 0회다.
- DB Router 활성화 시 reader로 라우팅된다.

### TX-003 쓰기 세션 [P0]

DB 변경 View와 조회 후 쓰기 유스케이스는 `get_writer_db_session` 기반 Service
Dependency를 사용해야 한다.

수용 기준:

- POST/PUT/PATCH/DELETE의 DB 쓰기가 read session으로 실행되지 않는다.
- 첫 SELECT부터 primary writer에 고정되어 replica lag의 영향을 받지 않는다.
- DB를 쓰지 않는 POST는 이유가 기록된 allowlist로 관리한다.

### TX-004 응답 전 commit [P0]

쓰기 성공은 View 본문에서 응답 반환 전에 정확히 한 번 commit해야 한다.

수용 기준:

- `await service.commit()`이 View의 성공 경로에 존재한다.
- commit 실패 시 클라이언트가 2xx를 받지 않는다.
- 예외 경로는 commit 0회다.
- Repository와 Dependency에 commit 호출이 없다.

### TX-005 DB session 명명 계약 [P0]

SQLAlchemy `AsyncSession`을 제공하거나 저장하는 애플리케이션 코드는 이름으로 DB 자원임을
명확히 표현해야 한다.

수용 기준:

- 정식 Dependency 이름은 `get_read_only_db_session`, `get_writer_db_session`,
  `get_routed_db_session`, `get_background_db_session`이다.
- 요청 밖 context manager는 `background_db_session`으로 명명한다.
- Dependency 인자와 Service/Repository 생성자 및 속성은 `db_session`을 사용한다.
- `session` 단독 이름은 SQLAlchemy 문맥이 명확한 제한된 내부 지역 변수에서만 허용한다.
- 기존 `get_read_session`, `get_write_session`, `get_session`, `get_background_session`은
  호출부 전환 기간에 deprecated alias로만 유지한다.
- 기존 이름 제거 전 전체 호출부와 Dependency override 테스트가 새 이름으로 전환된다.

## 11. Service 및 View 요구사항

### SVC-001 비즈니스 규칙 위치 [P0]

검증된 요청을 이용한 도메인 상태 전환, 기간 규칙, 중복 정책과 유스케이스 순서는
Service에 위치해야 한다.

수용 기준:

- 동일 유스케이스를 HTTP 외 경로에서 재사용할 수 있다.
- View에 데이터 접근 분기나 복잡한 도메인 조건이 없다.

### VIEW-001 버전별 파일 구성 [P1]

`v1` 이하에 업무 단위 View 파일을 여러 개 둘 수 있어야 한다.

수용 기준:

- 하나의 View 파일이 과도하게 커지면 resource 또는 use case 단위로 분리한다.
- 각 View 파일은 자체 `APIRouter`를 제공한다.
- 같은 버전의 그룹 `router.py`가 일관된 prefix와 tag로 취합한다.

### VIEW-002 ORM/Raw 응답 동등성 [P1]

ORM과 Raw View는 데이터 소스가 달라도 동일한 HTTP 품질 기준을 제공해야 한다.

수용 기준:

- 명시적 `response_model`을 사용한다.
- validation, 오류 상태와 pagination 형식이 프로젝트 기준과 일치한다.
- 내부 ORM 클래스 또는 Raw row가 응답 계약에 노출되지 않는다.

## 12. Scalar/OpenAPI 요구사항

### DOC-001 View 메타데이터 [P0]

모든 공개 path operation은 다음 정보를 제공해야 한다.

- `summary`
- 충분한 `description`
- 프로젝트 전체에서 고유한 `operation_id`
- 성공 `response_model`
- 성공 상태 코드
- 알려진 오류 `responses`
- 적절한 tag

204 응답은 body와 response model을 갖지 않는다.

### DOC-002 파라미터 문서 [P1]

Path, Query, Header와 요청 body는 설명, 실제 validation 제약과 대표 예시를 제공해야 한다.

수용 기준:

- 문서 제약과 런타임 Pydantic/FastAPI 검증이 일치한다.
- UUID, 날짜, pagination과 enum에 대표 예시가 있다.

### DOC-003 Pydantic schema [P0]

모든 외부 요청과 응답은 Pydantic 모델로 정의해야 한다.

수용 기준:

- 입력/출력 모델이 분리된다.
- 외부 노출 필드에 `description`이 있다.
- 주요 DTO에 `json_schema_extra.examples`가 있다.
- 민감 필드가 응답 schema에 포함되지 않는다.

### DOC-004 태그 메타데이터 정합성 [P0]

`app/core/tags_metadata.py`와 실제 Router tag를 동기화해야 한다.

수용 기준:

- 실제 사용되는 모든 tag가 metadata에 존재한다.
- 사용하지 않는 오래된 tag는 제거하거나 사유가 명시된다.
- `Auth`와 신규 예제 기능 tag가 포함된다.
- 구현 완료 기능에 “미구현/예정” 설명이 남아 있지 않는다.

### DOC-005 OpenAPI 자동 검증 [P1]

OpenAPI schema에 대한 자동 정합성 테스트를 제공해야 한다.

수용 기준:

- operation ID 중복을 탐지한다.
- tag metadata 누락과 미사용을 탐지한다.
- 204를 제외한 성공 응답의 response schema 누락을 탐지한다.
- ORM 및 Raw 예제 DTO schema가 OpenAPI에 생성된다.

## 13. 시나리오 요구사항

### SCN-ORM-001 상품 CRUD 예제 [P1]

ORM workflow를 설명하는 완결된 상품 CRUD 예제를 제공해야 한다.

포함 범위:

- Product ORM 모델과 migration
- create/list/get/update/delete
- ORM Repository, Service, read-only/writer DB session Dependency
- `v1/products.py`와 그룹 Router
- Pydantic 요청/응답 및 Scalar 문서
- Repository, Service, API, transaction 테스트
- `catalog_products` 실제 Alembic migration과 upgrade/downgrade 검증

### SCN-RAW-001 일별 매출 리포트 예제 [P1]

Raw workflow를 설명하는 일별 매출 집계 예제를 제공해야 한다.

포함 범위:

- 결과 전용 ORM 모델 없이 Raw 집계 SQL 사용
- named date parameters
- `SalesReportRawRepository`, Report Service, read-only Dependency
- Pydantic Raw 결과 DTO
- `v1/sales_reports.py`와 그룹 Router
- SQL 결과 mapping, reader routing, API, OpenAPI 테스트
- Raw 원본 `sales_orders` 실제 Alembic migration
- `compose.test.yaml`을 재사용하는 로컬 및 CI MySQL 통합 테스트

### SCN-RAW-002 Raw 쓰기 검증 예제 [P1]

운영 공개 API가 아니어도 테스트 fixture에서 Raw DML workflow를 검증해야 한다.

수용 기준:

- execute 결과 row count를 검증한다.
- 쓰기 commit 1회 및 실패 응답을 검증한다.
- read-only DML 차단을 검증한다.

## 14. 비기능 요구사항

### NFR-001 보안 [P0]

- SQL injection 방지 규칙을 위반하는 Raw SQL이 없어야 한다.
- 로그와 사용자 오류 응답에 비밀번호, 토큰, 전체 SQL 파라미터를 기록하지 않는다.
- Pydantic 응답에 비공개 ORM 필드가 포함되지 않는다.

### NFR-002 성능 [P1]

- 목록 API는 무제한 조회를 허용하지 않는다.
- pagination limit 상한을 둔다.
- ORM 관계 조회는 N+1 방지 전략을 기능 Repository에 명시한다.
- Raw 집계 쿼리는 실제 DB 실행 계획을 검토한다.
- 존재 확인은 SQL `EXISTS`를 사용한다.

### NFR-003 타입 안전성 [P1]

- ORM 모델, PK, Repository 반환 타입을 제네릭으로 검사한다.
- Raw 결과가 외부로 나가기 전에 Pydantic validation을 거친다.
- `Any`와 무검증 `dict` 반환을 Base의 공개 계약에서 최소화한다.

### NFR-004 관측성 [P1]

- Repository 오류 로그에 기능, 모델 또는 쿼리 이름을 포함한다.
- Raw SQL 전체 값과 민감 파라미터는 기록하지 않는다.
- 필요 시 느린 쿼리 관측을 위한 실행 시간을 구조화 필드로 남긴다.

### NFR-005 호환성 [P0]

- 기존 공개 API 경로, 응답 schema와 상태 코드를 의도 없이 변경하지 않는다.
- 기존 DB schema는 명시적 migration 없이 바뀌지 않는다.
- 기존 Base Repository 호출부를 점진적으로 전환한다.

### NFR-006 가용성 및 readiness [P1]

- liveness와 readiness의 역할을 분리한다.
- `/health`는 프로세스 생존 여부를 반환한다.
- `/ready`는 writer DB에서 `SELECT 1`을 실행하며 timeout은 2초다.
- 준비 완료는 200, DB 오류 또는 timeout은 503을 반환한다.
- 503 응답에 DSN과 내부 DB 오류 내용을 노출하지 않는다.
- 선택 자원의 미사용 상태를 장애로 판정하지 않는다.
- 필수 자원 startup 실패는 fail-fast한다.

### NFR-007 자원 예산 [P1]

- worker 수와 writer/read/background pool 크기를 곱한 최대 연결 수를 산정한다.
- DB 서버 최대 연결 수를 넘는 설정을 배포 전에 검수한다.
- multi-worker 환경에서 resource manager가 worker별로 실행됨을 문서화한다.

### NFR-008 lifecycle 관측성 [P1]

- startup/shutdown 단계와 소요 시간을 구조화 로그로 기록한다.
- 발견한 모델 모듈 수와 metadata table 수를 기록한다.
- 자원별 생성·close 성공과 실패를 기록한다.
- DSN password와 secret은 로그에 기록하지 않는다.

### NFR-009 Event loop 비차단 [P0]

비동기 선택지가 있는 I/O와 장시간 CPU 작업은 요청 event loop에서 직접 실행하지 않아야
한다.

수용 기준:

- 모든 공개 FastAPI path operation이 `async def`다.
- DB I/O는 `AsyncEngine`/`AsyncSession`과 async driver를 사용한다.
- bcrypt 같은 고비용 동기 CPU 작업은 `asyncio.to_thread()` 또는 worker로 격리한다.
- worker별 최대 10,000건의 bounded `QueueHandler`/`QueueListener`를 사용한다.
- production/staging 애플리케이션 파일 handler를 제거하고 stdout/stderr로 출력한다.
- Docker, Kubernetes 또는 운영 agent가 저장과 rotation을 담당한다.
- DEBUG/INFO/WARNING은 queue 포화 시 drop하고 counter를 증가시킨다.
- ERROR/CRITICAL은 queue 포화 시 최소 stderr fallback을 사용한다.
- console 및 uvicorn logging도 같은 queue 출력 경로로 통합한다.
- 동기 HTTP client, `time.sleep`, 동기 subprocess, 직접 파일 I/O를 async 함수에서 사용하지
  않는다.
- 짧은 User-Agent/JWT/Pydantic 연산은 측정 근거가 있는 한 동기 실행을 허용한다.
- SQLAlchemy `AsyncConnection.run_sync()`는 동기 DB driver 사용으로 판정하지 않는다.

## 15. 테스트 및 품질 게이트

### TEST-001 Base 단위 테스트 [P0]

ORM Base:

- CRUD primitive
- 입력 불변성
- PK 타입 및 not-found
- 예외 변환

Raw Base:

- one/all/scalar/execute 반환
- 빈 결과
- named parameter
- 예외 변환
- commit 미수행

### TEST-002 계층 및 트랜잭션 테스트 [P0]

- View가 올바른 Dependency를 사용한다.
- 조회는 writer session과 commit을 사용하지 않는다.
- 쓰기는 writer session과 응답 전 commit을 사용한다.
- Repository 및 Dependency commit을 탐지한다.

### TEST-003 API 통합 테스트 [P0]

- ORM/Raw 성공 응답
- 입력 validation 422
- not-found/conflict/DB 오류
- commit 실패가 2xx가 아님
- Pydantic 응답 계약

### TEST-004 전체 품질 게이트 [P0]

다음 명령이 모두 성공해야 한다.

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy .
```

### TEST-005 Lifespan 자원 관리 [P0]

- 모델 0개이면 table create와 DB 연결 시도가 0회인지 검증한다.
- 모델이 있고 개발 자동 생성 정책이 켜져 있을 때 create가 1회인지 검증한다.
- 운영 정책에서는 모델이 있어도 create가 0회인지 검증한다.
- startup 중 logging listener 등 후속 자원 초기화 실패 시 앞서 준비된 자원이 해제되는지 검증한다.
- 정상 shutdown의 drain/close/dispose 순서를 검증한다.
- cleanup 하나가 실패해도 나머지 cleanup이 실행되는지 검증한다.
- lifespan 재진입 후 task/listener/engine reference 누수가 없는지 검증한다.
- shutdown 후 `app.state.resources`에 닫힌 자원 reference가 남지 않는지 검증한다.
- background task 5초, DB dispose 10초, logging drain 5초와 FastAPI 전체 20초 제한을 검증한다.
- Celery worker cleanup의 별도 10초 제한을 검증한다.

### TEST-006 비동기 runtime 회귀 [P0]

- 모든 공개 path operation이 async 함수인지 검사한다.
- async 함수에서 금지된 동기 I/O 호출을 정적 검사한다.
- production/staging에 애플리케이션 file handler가 존재하지 않는지 검사한다.
- worker별 queue 크기 10,000과 non-blocking `put_nowait()`를 검증한다.
- 저레벨 drop counter, rate limit 및 ERROR/CRITICAL stderr fallback을 검증한다.
- listener startup, 정상 flush/stop, startup 실패 cleanup을 검증한다.
- drain timeout 시 pending task의 cancellation과 최종 task 집합 0개를 검증한다.
- Celery 연속 task가 동일한 살아 있는 loop를 재사용하는 기존 테스트를 유지한다.
- Celery worker shutdown 후 engine dispose, async generator shutdown, loop close를 검증한다.

## 16. 마이그레이션 요구사항

### MIG-001 기준선 확보 [P0]

변경 전에 다음 기준선을 확보해야 한다.

- 전체 테스트 결과
- ORM Base 공개 메서드와 사용처
- 현재 OpenAPI schema
- 현재 Alembic head 및 metadata/schema 비교

### MIG-002 단계적 적용 [P0]

다음 순서로 구현해야 한다.

1. Lifespan resource manager 및 모델 유무 분기
2. DB session Dependency 새 이름 추가 및 호출부 전환
3. 모델 mixin 계약과 schema 불변 검증
4. ORM Base 내부 개선 및 호환 wrapper
5. 기존 기능 Repository 전환
6. Raw Base 추가
7. ORM/Raw 예제 기능 추가
8. Scalar/OpenAPI 보강
9. 오래된 session/Repository 호환 이름 제거

기존 이름과 wrapper의 호환 기간은 릴리스 횟수가 아니라 단계 완료 조건으로 관리한다. 새
API 추가, 전체 호출부 전환, 사용처 0건 확인, 전체 품질 게이트 통과를 각각 독립 커밋으로
완료한 뒤 마지막 독립 단계에서만 제거한다.

### MIG-003 롤백 가능성 [P1]

각 단계는 독립 커밋으로 구성하고 API·DB schema 변경 여부를 명시해야 한다.

수용 기준:

- Raw Base 추가가 기존 ORM 동작과 결합되지 않는다.
- 모델 mixin 전환은 schema diff가 없으면 코드 단위로 되돌릴 수 있다.
- 호환 메서드는 모든 호출부 전환 전에 제거하지 않는다.

## 17. 제외 범위

다음은 본 작업의 요구사항이 아니다.

- View에서 직접 SQL 실행
- Service에서 SQL 문자열 생성
- Repository 내부 commit
- 자동 라우터 또는 Repository discovery
- ORM과 Raw 계층을 하나의 만능 Base로 통합
- Raw 결과를 검증 없는 dict로 외부 반환
- 모든 도메인 쿼리를 `app/core`로 이동
- API Gateway 또는 캐시 계층 도입
- 요청하지 않은 공개 API 호환성 파괴
- shutdown 시 DB table 삭제
- API Redis client/cache/readiness 구현
- Celery worker 자원을 FastAPI lifespan에서 제어
- 모든 짧은 CPU 연산을 무조건 thread pool로 넘기는 변경
- JWT access/refresh token 정책, rotation, revoke/logout 또는 권한 체계 구현

## 18. 요구사항 추적표

| 구현 단계 | 주요 요구사항 |
|---|---|
| Phase 0 기준선 | AR-001~004, MIG-001, NFR-005, ORM-REP-007 |
| Phase 1 Async Runtime/Lifespan | AR-005~010, TX-005, NFR-006~009, TEST-005~006 |
| Phase 2 모델 기반 | ORM-MDL-001~004, MIG-002 |
| Phase 3 ORM Repository | ORM-REP-001~007, TX-001~004, SVC-001, TEST-001~002 |
| Phase 4 Raw Base | RAW-REP-001~007, NFR-001~004 |
| Phase 5 예제 | SCN-ORM-001, SCN-RAW-001~002, VIEW-001~002 |
| Phase 6 Scalar | DOC-001~005 |
| Phase 7 최종 검수 | TEST-003~004, MIG-003 |

## 19. 완료 정의

다음 조건을 모두 만족해야 작업 완료로 판정한다.

- [ ] ORM과 Raw가 동일한 계층 호출 흐름을 사용한다.
- [ ] 모든 ORM Repository가 ORM Base 계층을 사용한다.
- [ ] 모든 Raw Repository가 Raw Base 계층을 사용한다.
- [ ] 모델 공통 필드 정책이 mixin으로 적용되고 DB schema가 의도 없이 바뀌지 않는다.
- [ ] 모델이 없으면 startup이 DB table 생성을 위한 연결을 시도하지 않는다.
- [ ] resource manager가 startup 실패와 shutdown에서 모든 소유 자원을 해제한다.
- [ ] background task drain → DB engine dispose → logging listener flush/stop 순서가 보장된다.
- [ ] API logging이 event loop에서 직접 file write/rotation을 수행하지 않는다.
- [ ] drain timeout 후 pending task가 취소·await되어 추적 집합에 남지 않는다.
- [ ] Celery worker 종료 시 async DB pool과 event loop가 정상 해제된다.
- [ ] View, Dependency, Service, Repository의 책임 위반이 없다.
- [ ] read-only/writer DB session 및 commit 경계가 자동 테스트로 보호된다.
- [ ] Raw SQL이 named binding과 식별자 allowlist 규칙을 준수한다.
- [ ] ORM/Raw 외부 응답이 모두 Pydantic DTO로 검증된다.
- [ ] ORM 상품 CRUD와 Raw 매출 리포트 예제가 완결되어 있다.
- [ ] Scalar에서 요청·응답·오류·파라미터·태그 문서가 정확하다.
- [ ] operation ID와 tag metadata 정합성 테스트가 통과한다.
- [ ] 전체 pytest, Ruff, format check, mypy가 통과한다.

## 20. 확정 정책

1. UUID, created, updated 책임은 작은 Mixin으로 분리한다.
2. ORM Repository는 `BaseRepository[ModelT, PrimaryKeyT]`를 정식 계약으로 사용한다.
3. Base에는 최소 CRUD만 두고 고급 쿼리는 기능 Repository로 이동한다.
4. OpenAPI는 규칙 기반 검증을 중심으로 하고 핵심 schema만 snapshot한다.
5. `/ready`는 writer DB `SELECT 1`, 2초 timeout, 성공 200, 실패 503을 사용한다.
6. FastAPI shutdown은 task 5초, DB 10초, logging 5초, 전체 20초를 사용한다.
7. Celery worker cleanup timeout은 별도 10초다.
8. logging은 worker별 10,000건 queue와 stdout/stderr 외부 collector 방식을 사용한다.
9. queue 포화 시 저레벨 로그는 drop하고 ERROR/CRITICAL은 제한된 stderr fallback을 사용한다.
