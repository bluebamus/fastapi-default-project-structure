# AUDIT LEDGER (append-only)

> 이 원장은 감사 실행 전반에 걸쳐 append-only로 유지된다. 코드를 바꾸는 모든 작업 단위마다
> 커밋 해시·시각·대상·변경 전후·결정 근거·검증 결과·회귀 위험을 기록한다(§5.6 규칙).

---

## 실행 #1 — 2026-07-08 · 브랜치 `audit/full-review-2026-07-08`

### 0단계 · 안전 준비 결과
- 작업 트리: clean, 시작 브랜치 `main` (HEAD `3ff01f2`).
- 원장: 기존 `AUDIT_LEDGER.md` 없음 → 본 파일 신규 생성.
- 패키지 매니저: **uv** (uv.lock 존재). Python 3.14.4 venv.
- 베이스라인 테스트: **78 passed, 0 failed** (`uv run python -m pytest`).
  - 환경 주의: `uv run pytest`(콘솔 스크립트 shim)는 slowapi를 못 찾아 실패하지만
    `uv run python -m pytest`는 정상. shim 인터프리터 불일치 추정 — 코드 버그 아님, 환경 이슈.

### 1단계 · 정적 분석 스캔(수정 전 read-only 측정)
- **Ruff check** (설정 룰셋 E/W/F/I/B/C4/UP): `All checks passed`.
- **Ruff format --check**: 69개 파일 재포맷 대상(대부분 공백/개행) — 대규모 diff, 적용 전 별도 승인 대상.
- **Ruff S(보안) 룰** 별도 스캔: S101 assert 159(대부분 테스트, 무해) / S105·S106·S107 하드코딩 pw 7(대부분 테스트 픽스처·에러코드 상수 오탐) / S104 bind-all 1.
- **mypy**: 60 errors / 16 files (147 소스 체크). 주요 군집:
  - `responses=` dict 타입 불일치 `dict[int, dict[str, object]]` (~18건, 다수 라우터 공유 상수).
  - `main.py` slowapi import-not-found (mypy override 누락).
  - `repository_base.py` `Result.rowcount` attr-defined + no-any-return.
  - `user_info_middleware.py` add_middleware 팩토리 타입 불일치.
  - `home/admin.py` 모델 컬럼을 `type`에서 접근(is_bot 등).
  - `auth.py` get_user_by_id 인자 `Any|None` vs `str`.
- **Bandit** (설치: bandit==1.9.4, dev): MEDIUM+ 실질 1건 = B104 `main.py:300` bind 0.0.0.0(서버 바인딩, 의도적일 가능성). 나머지 LOW는 테스트 assert/오탐.

### 작업 단위 로그 (1단계)

#### WU-1 · `042401b` chore(dev): add bandit
- 대상: pyproject.toml, uv.lock. bandit==1.9.4 dev 추가(스캔 도구). 코드 무변경.
- 검증: — (도구 추가). 회귀: 신규.

#### WU-2 · `bddecae` style(format): ruff format 전체
- 대상: 69파일. 공백/개행 정규화, 동작 무변경.
- 결정: 이후 로직 diff 를 포맷 노이즈와 분리하기 위해 최우선 단일 커밋.
- 검증: ruff check All passed, pytest 78 passed. 회귀: 신규(무해).

#### WU-3 · `305e535` fix(repo): 중첩 eager-loading + rowcount 타이핑
- 대상: repository_base.py, models_base.py.
- 변경 전 문제:
  1) `_apply_eager_loading` 중첩관계 2번째 파트를 str 로 selectinload() 전달 →
     SQLAlchemy 2.0 에서 런타임 오류(문자열 관계 로딩 제거). **실제 잠재 버그.**
  2) DML `result.rowcount` 가 `Result` 타입에 없어 mypy attr-defined(6건).
  3) 제네릭 `self.model.id` 가 `type[ModelType]`(bound=Base, id 없음)에서 막힘(9건).
- 결정/근거:
  1) mapper 를 따라 관련 모델의 실제 관계 속성으로 해석(동작 변경 = 버그 픽스).
     현재 프로덕션 호출부에 중첩관계 사용 없음(docstring 예시뿐) → 실사용 회귀 위험 0.
  2) `cast("CursorResult[Any]", ...)` — 런타임 반환 타입과 일치, 동작 동일.
  3) `Base` 에 `if TYPE_CHECKING: id: Mapped[str]` — 런타임 매핑 무영향, 불변식 문서화.
- 검증: mypy 0, ruff clean, pytest 78 passed. 회귀: 없음(1은 개선/버그픽스).

#### WU-4 · `0df11c9` fix(types): 잔여 mypy 전부 해결(# type: ignore 없이)
- 대상: 6개 라우터, pagination, auth util/router, filters, celery/tasks,
  user_info_middleware, home/admin, pyproject(mypy override).
- 핵심: responses 상수 타입 명시, TypeVar 바운드(T→BaseModel, ModelT→Base),
  bcrypt 반환 확정, refresh sub isinstance 가드(방어 강화, 401 동일),
  frame FrameType|None, run_async 결과 dict 확정, 미들웨어 ASGIApp/
  RequestResponseEndpoint, admin 포매터 명명 함수화, override 에 slowapi/bcrypt/celery.
- 검증: mypy Success(0/147), ruff clean, pytest 78 passed. 회귀: 없음.

#### WU-5 · `0f3d9d4` fix(security): dev 서버 바인딩 설정화(B104)
- 대상: config.py, main.py, .env.example.
- 변경 전: main.py 하드코딩 host=0.0.0.0/port=8000(bandit B104 MEDIUM).
- 결정/근거: 컨테이너 실행 전제라 0.0.0.0 을 조용히 127.0.0.1 로 바꾸면 의도된 실행이
  깨짐 → SERVER_HOST/SERVER_PORT 설정으로 외부화(기본값 유지=동작 보존), 민감 환경은
  env 로 제한 가능. config 기본값에 `# nosec B104` 정당화. **완전 차단은 human-decision.**
- 검증: bandit MEDIUM+ 0, ruff/mypy clean, pytest 78 passed. 회귀: 없음.

### 작업 단위 로그 (2·5단계)

#### WU-6 · `f850393` fix(async): bcrypt 스레드 격리
- 대상: app/domains/auth/services/auth_service.py.
- 변경 전: register/authenticate 가 async 경로에서 bcrypt 동기 호출 → 이벤트 루프
  수백 ms 블로킹(동시 로그인/가입 시 전체 지연). **§2 async 블로킹 실제 이슈.**
- 결정/근거: `asyncio.to_thread` 로 hash/verify 격리(결과 동일, 논블로킹). authenticate 는
  is_active 검사를 verify 앞으로 옮겨 비활성 계정 bcrypt 생략(최종 401 동일).
- 검증: ruff/mypy clean, pytest 78 passed(auth 18). 회귀: 없음(성능 개선).

#### WU-7 · `7700662` docs: README 드리프트 정정
- 대상: README.md. 코드/파일 실제 상태를 기준으로 문서 정정(§5.4).
  - `.env.sample`→`.env.example`(실제 파일명), authenticator '스텁'→실제 JWT/bcrypt,
    인증·레이트리밋 기능/스택 추가, 아키텍처 예외(auth→user, core→도메인 models) 명시.
- 검증: 코드 무변경(문서). 회귀: 없음.

### §5 설계·정합성 검수 결과(요약 — 상세는 AUDIT_REPORT.md)
- 계층 경계(router→service→repository, 의존성 커밋)는 실제로 준수됨.
- 도메인 격리: auth→user 만 교차 import(코드에 문서화된 횡단 예외). 나머지 격리.
- core↛domains: session.py `create_db_tables`(DEBUG 전용, 함수 내부) 예외 1곳.
- N+1: 도메인 모델에 ORM relationship 없음 → 현재 N+1 불가(eager 인프라는 미사용 제네릭).
- 미적용(설계 결정 필요)로 남긴 항목: CORS `*`+credentials 가드, 사용자 열거 타이밍
  사이드채널, update 존재확인 중복 쿼리, B104 완전차단 여부.

---

## 회귀 방지 비교 검수 표 (§5.6.2)

과거 작업(원장은 이번이 최초이므로 git 커밋 이력에서 식별)과 이번 변경의 대조:

| 항목 | 이전 작업의 상태·문제 인식 | 이번 변경의 상태·문제 인식 | 회귀 여부 | 판단·근거 |
|---|---|---|---|---|
| Celery 이벤트 루프 (C1) | `52f..`/`a295643`: 매 호출 asyncio.run→"loop closed". 영속 루프로 해결 | 건드리지 않음. tasks.py 는 타입만 명시(run_async 결과 dict) | 회귀 없음 | task.py 로직 무변경, run_async 그대로 사용 |
| 읽기전용 auth no-commit (W2) | `52f5..`: get_current_user 이중커밋 위험→커밋 제거 | 유지. auth 라우터는 타입/가드만 추가 | 회귀 없음 | get_auth_service/get_current_user 커밋 정책 불변 |
| 백그라운드 태스크 상한+drain (W1) | `52f5..`: 무제한 증가·유실→상한+lifespan drain | 건드리지 않음 | 회귀 없음 | background_tasks.py 무변경 |
| bcrypt 호출 방식 | (기존) 동기 호출 | to_thread 격리로 변경 | 회귀 아님(개선) | 결과 동일, 이벤트 루프 논블로킹. 과거에 '동기라야 한다'는 결정 근거 없음 |
| 중첩 eager-loading | (기존) 문자열 selectinload — SQLAlchemy 2.0 미동작(잠재) | mapper 로 속성 해석하도록 수정 | 회귀 아님(버그픽스) | 프로덕션 미사용(문서 예시만) → 실사용 영향 0, 문서화된 기능 실동작화 |
| dev 서버 바인딩 | (기존) 하드코딩 0.0.0.0 | 설정화(기본값 0.0.0.0 유지) | 회귀 없음 | 기본 동작 보존, env 오버라이드만 추가 |

> 이전 감사(W1/W2/C1)에서 '문제'로 식별해 해결한 상태로 **의도치 않게 되돌아간 변경 없음**.
> 이번 변경은 전부 신규 개선이거나 과거 결정과 독립적.

---

## 실행 #1 (후속) — 보류 항목 처리 · 2026-07-08

사용자 승인("진행해줘")에 따라 §5 보류 4건을 재검토·처리.

#### WU-8 · `9cecf2b` fix(security): CORS 가드 + 상수시간 인증 (보류 #1·#2 적용)
- 대상: config.py(CORSSettings), auth_service.py, tests/core/test_cors_settings.py(신규).
- #1 CORS: `['*']`+credentials=True 조합을 `model_validator` 로 기동 시 거부(fail-fast).
  안전 조합(`*`+credentials=False, 구체Origin+credentials=True)은 허용. 테스트 3케이스.
- #2 상수시간 인증: 사용자 부재/비번 미설정 시에도 더미 해시로 항상 bcrypt 검증 →
  응답 시간차 제거(사용자명 열거 방지). 결과 401 동일.
- 검증: ruff/mypy clean, pytest 81 passed(+3). 회귀: 없음(안전 조합·정상 로그인 불변).

#### 보류 #3 (update 중복 쿼리) — **미적용, 근거와 함께 보류 유지**
- 재분석: 사전 존재확인 `get_*` 는 제거하면 안 됨. 오히려 그 뒤에 **MySQL 전용 잠재 버그**
  발견 — aiomysql 은 `CLIENT_FOUND_ROWS` 미설정이라 rowcount=변경행. 동일 값 PATCH 시
  rowcount=0 → `repository.update` 가 None → 서비스가 **잘못된 404** 반환.
- 테스트가 이를 못 잡는 이유: 테스트는 SQLite(aiosqlite)로 돌고, SQLite 는 no-op UPDATE
  도 rowcount=1 을 반환해 문제를 가림. 즉 **현재 CI 로 회귀 검증 불가**.
- 판단: 수정은 동작 변경(no-op PATCH MySQL 에서 404→200)이며 회귀 검증 수단이 없어
  **자동 적용하지 않고 설계 결정 필요로 승격**. 권고안: 서비스에서 존재확인 후 update 가
  None 이면 404 대신 현재 엔티티 반환(4개 도메인 동일), 또는 커넥션에 CLIENT_FOUND_ROWS.

#### 보류 #4 (B104 완전 차단) — **미적용, 기본값 유지**
- 기본 바인딩을 127.0.0.1 로 강제하면 컨테이너 외부 접근이 막혀 의도된 실행이 깨짐.
  이미 `SERVER_HOST` 로 설정 가능하므로 코드 변경 불요. 운영 제한은 배포 시 env 로 결정.

> 회귀 대조: 보류 #3/#4 미적용은 과거 결정 회귀 아님(신규 발견 문서화). #1/#2 는 신규 보안 강화.

#### WU-9 · `0bcab15` fix(update): no-op PATCH 404 수정 (M4, 사용자 승인 후 적용)
- 대상: blog/user/reply/sns services 의 update_*, tests/domains/test_update_noop.py(신규).
- 변경 전: 존재확인 후 `repository.update` 가 None 이면 404. MySQL 은 동일 값 UPDATE 시
  rowcount=0 → None → 존재하는 리소스에 no-op PATCH 시 **잘못된 404**.
- 결정/근거: 존재는 이미 `get_*` 로 보장 → update 가 None 이면 404 대신 현재 엔티티 반환.
  [동작 변경] MySQL no-op PATCH: 404→200. SQLite 는 no-op 도 rowcount=1 이라 불변.
- 테스트: repository 스텁으로 no-op(None)/부재(get_by_id=None) 분리 검증 8건(4×2).
  현재 SQLite 하니스에서 실행 확인(사용자 지시: 현재 환경에서만 테스트).
- 검증: ruff/mypy clean, pytest 89 passed(+8). 회귀: 없음(SQLite 경로 불변).

#### 최종 Bandit 감사 (사용자 지시: 모든 단계 후)
- 명령: `bandit -r app main.py config.py` (전체 5,740 LOC).
- 결과: **High 0 / Medium 0**. Low 96 = B101 assert 89(테스트) + B105 6(오탐: 토큰
  종류 식별자·에러코드 상수) + B106 1(테스트 픽스처). #nosec 처리 1(B104 정당화).
- 결론: **실질 보안 이슈 0건**. Low 는 전부 테스트 assert 또는 문자열 상수 오탐.

> 보류 #4(dev 바인딩 완전차단)는 nginx/리버스 프록시로 설정 가능한 영역이라 사용자
> 지시에 따라 제외(코드 기본값 0.0.0.0 유지, SERVER_HOST 로 이미 제한 가능).

---

## 실행 #1 (후속2) — 페이지네이션 유틸 재구성 · 2026-07-08

#### WU-10 · `0469c25` refactor(pagination): utils 로 이동 + 순수 dataclass
- 요청: 페이지네이션을 utils 폴더에 별도 모듈·클래스로, 데이터클래스로 초기값 정의,
  return cls() 에 쓸 클래스 변수만 정의(반환 타입 고정). 안티패턴 있으면 확인.
- 안티패턴 검토 → 사용자 확인:
  - (Q1) 응답스키마를 순수 dataclass 로 → 트레이드오프 안내 후 **순수 @dataclass 선택**.
    현재 미사용이라 즉시 리스크 없음.
  - (Q2) 배치 → **app/utils/pagination/ 이동** 선택.
  - 자동 처리: items 가변 기본값 → field(default_factory)(안티패턴 회피), __init__ wildcard
    import 제거(명시적 export).
- 변경 전 상태: app/shared/pagination/ 의 PaginatedResponse(Pydantic Generic)+get_paginated
  (DB/Pydantic 결합). **앱 전체 미사용(grep 확인, 테스트 0) = 데드코드.** shared 계층은
  pagination 만 보유.
- 결정/근거:
  - 순수 Pagination[T] dataclass 를 app/utils/pagination/ 에 신규(무의존, utils 순수성 준수).
  - app/shared/ 전면 제거(참조 0 확인). get_paginated 는 미사용+DB결합이라 utils 순수성
    위반 → 드롭(검증된 데드코드, 안전 삭제). **capability 감소 인지**: 향후 DB 페이지네이션
    헬퍼가 필요하면 재도입 가능(현재 도메인은 자체 skip/limit 스키마 사용).
  - 문서 정합성(코드 기준): README/ARCHITECTURE 의 shared→utils, 의존방향, stale 한
    app.shared.logging→app.utils.logs, 미존재 로거상수 섹션→실제 get_logger 패턴,
    authenticator 스텁→구현. filters 의 죽은 /app/shared/ 세그먼트 제거.
- 검증: ruff clean, mypy 0(146), pytest 95 passed(+6), bandit MEDIUM+ 0(신규 파일 이슈 0).
- 회귀: 없음. 미사용 코드 제거 + 신규 순수 유틸. 과거 결정과 독립.
