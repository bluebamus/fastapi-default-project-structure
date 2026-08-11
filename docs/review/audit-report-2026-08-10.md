# fastapi-default-project-structure 검수 보고서

작성일: 2026-08-10

## 검수 대상

- 저장소: `fastapi-default-project-structure`
- 목적: FastAPI 일반 목적 프로젝트의 기본 구조로 적합한지 검토
- 주요 검토 관점:
  - FastAPI 표준 배선과의 정합성
  - 디자인 패턴 구현 수준
  - 확장성, 재사용성, 구조화 수준
  - 신규 도메인 추가 가이드
  - 테스트 및 정적 검사 안전망

## 종합 판정

`fastapi-default-project-structure`는 FastAPI의 일반적인 다중 파일 애플리케이션 구조와 잘 맞는다. 각 도메인 패키지가 `APIRouter`를 구성하고, `main.py`가 `include_router()`로 최종 취합하는 방식은 FastAPI 공식 문서의 "Bigger Applications" 패턴과 같은 방향이다.

다만 이름과 달리 단순한 "기초 템플릿"이라기보다는 MySQL, Redis, Celery, SQLAdmin, JWT 인증, rate limit, DB read/write routing까지 포함한 프로덕션 지향 백엔드 스타터에 가깝다. 따라서 범용 기본 구조로 배포하려면 최소 구성과 확장 구성을 분리하는 것이 좋다.

## 확인된 구조

핵심 애플리케이션 배선은 다음 흐름을 따른다.

```text
main.py
  -> APPS 목록
  -> 각 app.domains.<name>.router
  -> app.include_router(..., prefix="/api")
```

도메인 내부는 다음 계층으로 구성되어 있다.

```text
Router -> Dependency -> Service -> Repository -> Database
```

대표 디렉터리 구조:

```text
app/
  core/       공통 인프라, DB 세션, 미들웨어, 예외, base class
  domains/    기능 단위 도메인 앱
  utils/      로깅, 인증, 페이지네이션 등 공통 유틸리티
  celery/     중앙 Celery 앱과 태스크 브릿지
```

## 긍정 평가

### 1. FastAPI 표준 배선 준수

`main.py`의 `APPS` 목록과 `include_router()` 루프를 통해 라우터를 명시적으로 취합한다. 자동 스캔이나 숨은 registry에 의존하지 않아 로딩 순서와 공개 API 구성이 추적 가능하다.

### 2. 계층 분리 명확

라우터는 HTTP 입출력과 의존성 주입에 집중하고, 비즈니스 로직은 Service, 데이터 접근은 Repository로 분리되어 있다. 이 구조는 API가 늘어날수록 파일 책임을 유지하기 쉽다.

### 3. 트랜잭션 경계가 패턴화되어 있음

각 도메인의 `get_<name>_service` 의존성이 세션을 받아 Service를 생성하고, 요청 성공 시 `session.commit()`을 수행한다. 예외 발생 시 `get_session()` teardown에서 rollback하는 구조다.

### 4. 확장 가이드와 스캐폴딩 제공

`scripts/new_app.py`가 신규 도메인 디렉터리, 라우터, 의존성, 선택적 admin 파일을 생성한다. README와 `docs/ARCHITECTURE.md`에도 신규 모듈 추가 절차와 체크리스트가 문서화되어 있다.

### 5. 테스트 안전망이 충분함

라우트 인벤토리, 도메인 endpoint, DB routing, settings contract, admin 노출, 스캐폴딩 테스트가 존재한다. 구조 변경 시 공개 API나 도메인 등록 누락을 잡을 가능성이 높다.

## 주요 리스크

### 1. 일반 목적 기본 템플릿치고 무거움

기본 의존성에 MySQL, Redis, Celery, SQLAdmin, JWT, slowapi, read/write routing이 포함되어 있다. 일반적인 FastAPI 입문/기초 프로젝트 구조로는 초기 인지 비용과 운영 전제 조건이 많다.

권장 개선:

- `minimal`: FastAPI + Pydantic + pytest
- `api-db`: SQLAlchemy + Alembic 포함
- `production`: Celery, Redis, SQLAdmin, rate limit, DB routing 포함

처럼 프로필을 분리한다.

### 2. 신규 도메인 등록이 여러 위치에 분산됨

스캐폴딩 이후 다음 파일을 수동으로 수정해야 한다.

- `main.py`: `from app.domains import ...` 및 `APPS` 목록
- `migrations/env.py`: Alembic autogenerate용 model import
- `app/core/db/session.py`: DEBUG 모드 `create_db_tables()`용 model import
- 각 도메인 `__init__.py`: model import 주석 해제

문서에는 명시되어 있으나 누락 가능성이 있다.

권장 개선:

- `scripts/new_app.py`가 `--register` 옵션으로 `main.py`, `migrations/env.py`까지 갱신
- 등록 누락을 검출하는 테스트 추가
- 도메인 model import 목록을 단일 SSOT로 통합

### 3. FastAPI 업그레이드 시 yield dependency 트랜잭션 경계 점검 필요

현재 프로젝트는 FastAPI `0.115.14` 계열에 고정되어 있고, `Depends()`에 `scope` 인자가 없다. 최근 FastAPI 문서에서는 `yield` dependency의 종료 코드 실행 시점과 `scope="function"` 옵션을 명시한다.

현재 구조는 `yield` 이후 `session.commit()`에 의존하므로 FastAPI 버전 업그레이드 시 다음을 확인해야 한다.

- 커밋 실패가 응답 전송 전에 발생하는지
- 응답 성공 후 커밋 실패로 데이터 불일치가 생기지 않는지
- 쓰기 endpoint에 대해 명시적인 transaction context 또는 `scope="function"` 전환이 필요한지

### 4. 정적 타입 검사 1건 실패

`ruff`는 통과했지만 `mypy`는 다음 타입 오류가 확인되었다.

```text
main.py:261: Argument 2 to "add_exception_handler" of "Starlette" has incompatible type ...
```

원인은 `slowapi`의 `_rate_limit_exceeded_handler` 타입 시그니처가 Starlette의 `add_exception_handler()` 기대 타입과 정적으로 맞지 않는 점이다. 런타임 테스트는 통과하지만 타입 게이트를 CI에 걸려면 래퍼 함수나 명시적 cast가 필요하다.

## 검증 결과

실행한 검증:

```text
.\.venv\Scripts\python.exe -m pytest --basetemp .pytest_tmp
```

결과:

```text
177 passed
```

정적 검사:

```text
.\.venv\Scripts\python.exe -m ruff check .
```

결과:

```text
All checks passed
```

타입 검사:

```text
.\.venv\Scripts\python.exe -m mypy . --cache-dir .mypy_tmp
```

결과:

```text
1 error in main.py
```

참고: 샌드박스 내부에서는 pytest/mypy 캐시 및 임시 디렉터리 권한 문제로 일부 명령이 실패했으나, 권한 밖 실행에서는 pytest 전체가 통과했다.

## 문서화 수준 평가

README와 `docs/ARCHITECTURE.md`는 다음 내용을 이미 제공한다.

- 프로젝트 목적과 기술 스택
- 도메인 앱 표준 레이아웃
- 계층별 책임
- 신규 모듈 생성 및 등록 절차
- 환경 변수와 DEBUG/ADMIN 동작
- Alembic, Celery, SQLAdmin, access log 구조
- 테스트 실행 명령

다만 문서와 구조가 풍부한 만큼, 기본 사용자에게는 "먼저 무엇만 알면 되는지"가 약하다. 일반 목적 템플릿으로 사용할 경우 `QUICKSTART`나 `minimal profile` 문서를 별도로 두는 편이 낫다.

## 우선순위별 개선안

### P1

- `mypy`의 `main.py` slowapi handler 타입 오류 수정
- FastAPI 업그레이드 전 `yield` dependency 커밋 시점 검증 테스트 추가

### P2

- `scripts/new_app.py --register` 옵션 추가
- 신규 도메인 등록 누락을 탐지하는 테스트 강화
- Alembic model import와 DEBUG table creation import의 중복 제거

### P3

- 템플릿 프로필 분리: `minimal`, `api-db`, `production`
- README에 "처음 보는 사용자를 위한 최소 실행 경로" 추가
- Celery/SQLAdmin/DB routing은 선택 기능으로 명확히 분리

## 최종 결론

이 저장소는 FastAPI 표준 배선, 계층 분리, 테스트 안전망, 확장 가이드 측면에서 실무형 스타터로 사용할 수 있다. 다만 "기본 구조"라는 이름에 비해 포함 기능이 많고, 신규 도메인 등록 절차가 수동으로 분산되어 있어 범용 템플릿으로 쓰려면 경량화와 자동화가 필요하다.

