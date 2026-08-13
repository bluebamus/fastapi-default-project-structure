# Charter — orm-raw-repository  (Charter v0.1 / 2026-08-13)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 영역/하위시스템 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 애플리케이션 조립 | `main.py`, `config.py` | 소스 | lifespan·라우터 취합·설정 |
| 자원 관리 | `app/core/resources.py` | 소스 | **Phase 1 신규** |
| DB 세션·라우팅 | `app/core/db/` | 소스 | session/router/models_registry |
| 모델 기반 | `app/core/models/models_base.py` | 소스 | Phase 2 Mixin 대상 |
| ORM Repository Base | `app/core/repositories/crud_base.py`, `repository_base.py` | 소스 | Phase 3 대상 |
| Raw Repository Base | `app/core/repositories/raw_crud_base.py`, `raw_repository_base.py` | 소스 | **Phase 4 신규** |
| Service Base | `app/core/services/services_base.py` | 소스 | |
| 미들웨어·로깅 | `app/core/middlewares/`, `app/utils/logs/` | 소스 | Phase 1 Queue 전환 대상 |
| 태그 메타데이터 | `app/core/tags_metadata.py` | 소스 | Phase 6 대상 |
| 기존 기능 6종 | `app/features/{auth,blog,home,reply,sns,user}/` | 소스+테스트 | 회귀 보호 대상 |
| 신규 기능 2종 | `app/features/{catalog,reports}/` | 소스+테스트 | **Phase 5 신규** |
| Celery | `app/celery/` | 소스 | Phase 1 worker 종료 대상 |
| 마이그레이션 | `migrations/` | 소스 | Phase 5 revision 2개 추가 |
| 공통 테스트 | `tests/` | 테스트 | |
| MySQL 통합 환경 | `compose.test.yaml` | 설정 | **Phase 5 신규**, mysql:8.4 / 3307 |
| 문서 | `README.md`, `docs/ARCHITECTURE.md`, `docs/QUICKSTART.md` | 문서 | Phase 7 갱신 |

기준선 실측 (2026-08-13, 커밋 `a980b71` + 인코딩 수정):

- 소스 `.py` 146개 · 테스트 파일 52개 · 테스트 201개 (201 collected / 201 passed)
- OpenAPI: paths 18 · operations 30 · operationId 누락 0 · 중복 0
- Alembic head: `b2f1a9c0d3e4` · revision 2개
- 실사용 tag: Auth, Blog, Health, Home, Reply, SNS, User
- 상세: `baseline/openapi.json`, `baseline/survey.txt`

## 2. 계약 (Contract)

### 2-1. 지원 구성

- Python 3.14 · FastAPI · SQLAlchemy 2.x async · aiomysql(운영) / aiosqlite(단위 테스트)
- 환경: `ENV=development|test|staging|production`, `DEBUG`, `ADMIN`, `DB_ROUTER_ENABLED`, `DB_REPLICATION_ENABLED`
- MySQL 통합 테스트: `compose.test.yaml` 의 mysql:8.4, 호스트 포트 **3307** (WSL Docker)

### 2-2. 위협 모델

- 방어한다: Raw SQL injection(값·식별자 양쪽), 응답으로의 민감 필드 노출, 로그로의 SQL 파라미터·secret 유출, 조회 경로의 의도치 않은 쓰기, 커밋 실패의 2xx 둔갑
- 방어하지 않는다: Admin 무인증 노출(설계상 수용 — 배포 환경변수/프록시 책임), JWT rotation·revoke(범위 밖), 인가·권한 모델(범위 밖)

### 2-3. 불변식 (Invariants)

- **INV-1**: View 가 `AsyncSession` 을 직접 주입받지 않고, View·Service 가 `session.execute()` 를 직접 호출하지 않는다. (AR-001)
- **INV-2**: Repository 와 Dependency 는 `commit()` 하지 않는다. 쓰기 성공 경로는 View 본문에서 응답 전 정확히 1회 커밋한다. (TX-001/004)
- **INV-3**: GET/HEAD 는 read-only 세션을 쓰고 커밋 0회. 쓰기는 writer 세션. (TX-002/003)
- **INV-4**: Raw SQL 의 외부 값은 named bind parameter, 식별자는 코드 소유 allowlist 에서만 선택. (RAW-REP-003/004)
- **INV-5**: `RawRepositoryBase` 가 `BaseRepository` 를 상속하지 않는다. 두 Base 는 독립 계층. (AR-003)
- **INV-6**: 외부 응답은 전부 Pydantic DTO 검증을 거친다. `Row`/`RowMapping`/ORM 객체가 응답 계약에 노출되지 않는다. (RAW-REP-005, VIEW-002)
- **INV-7**: 모델 metadata table 이 0개면 startup 이 DB 연결·`create_all()` 을 시도하지 않는다. 운영에서는 모델이 있어도 `create_all()` 을 실행하지 않는다. (AR-007)
- **INV-8**: startup 중간 실패에서도 이미 만든 자원이 해제된다. 종료 순서는 background drain → DB dispose → logging flush/stop. (AR-008)
- **INV-9**: drain timeout 후 pending task 는 cancel + await 되어 추적 집합이 빈다. (AR-009)
- **INV-10**: 모든 공개 path operation 이 `async def` 이고, 요청 event loop 에서 동기 파일 I/O 를 하지 않는다. (NFR-009)
- **INV-11**: 기존 공개 API 경로·응답 schema·상태 코드가 의도 없이 바뀌지 않는다. (NFR-005)
- **INV-12**: 라우터는 자동 발견 없이 `v1/<view>.py → router.py → feature/__init__.py → main.py` 로 명시 취합된다. (AR-004)

### 2-4. 비목표

- View 직접 SQL 실행 / Service 의 SQL 문자열 생성 / Repository 내부 commit
- 자동 라우터·Repository discovery
- ORM·Raw Base 통합
- API Redis client/cache/readiness, JWT token lifecycle, 권한 체계
- FastAPI lifespan 이 Celery worker 자원을 종료
- shutdown 시 DB table drop
- 짧은 CPU 연산의 무조건 `to_thread()` 전환

## 3. 인수 기준 (Acceptance Criteria) — GATE 3

- [ ] 전 테스트 실제 실행·통과 (기준선 201개 이상, 조용한 SKIP 아님 — MySQL 마커 skip 은 사유 기록)
- [ ] `ruff check .` / `ruff format --check .` / `mypy .` 클린
- [ ] INV-1 → 계층 위반 정적 검사 테스트 / INV-2·3 → commit 횟수·세션 종류 테스트
- [ ] INV-4 → injection 입력 테스트 + 식별자 allowlist 테스트
- [ ] INV-5 → 상속 관계 부재 단정 테스트
- [ ] INV-6 → 응답 schema 계약 테스트 + OpenAPI 노출 검사
- [ ] INV-7·8·9 → lifespan 테스트(모델 0/1+, startup 실패 cleanup, 종료 순서, 재진입 누수)
- [ ] INV-10 → 전 path operation async 검사 + 금지 동기 I/O 정적 검사
- [ ] INV-11 → `baseline/openapi.json` 대비 기존 30개 operation 의 경로·상태 코드 불변 확인
- [ ] INV-12 → 라우터 등록 누락 탐지 테스트가 신규 기능 2종을 포함
- [ ] Alembic: 신규 revision 2개의 upgrade → downgrade → 재-upgrade 가 MySQL 8.4 에서 통과
- [ ] 질의 수준(design-baseline §0 = 보통)이 P/D 질문 깊이에 반영됨

## 4. 변경 이력

- v0.1 (2026-08-13): 최초 작성. 기준선 실측 반영, INV-1~12 확정.
