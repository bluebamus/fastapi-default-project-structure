# Ledger — docs-guide-site (지적 원장)

> 검수 지적 ID → 처리 → 커밋. 원본 커밋 `b439092`. 계약 테스트 `b0cb53b`. 코드 근거는 고치기 전에 다시 열어 확인했다.
> 42건 모두 처리. 지적 일부 정정 1건(OPS-02 의 Redis 503 범위 — 감독 정정, 코드·README 기준).

| ID | 심각도 | 문서 | 고친 것(코드 근거) | Status | 커밋 |
|---|---|---|---|---|---|
| FEA-01 | HIGH | features 8편 "라우터에서 직접 commit 안 함" | 쓰기 핸들러가 DTO 검증 뒤 `await service.commit()` 1회(blog.py `create_post`, `tests/test_write_dto_before_commit.py`) | Fixed | `ea2fd46` |
| FEA-02 | MED | features 8편·architecture "서비스가 트랜잭션 책임" | 트랜잭션 경계 = 핸들러 본문(session.py `get_routed_db_session` 주석, services_base) | Fixed | `ccdd874`, `ea2fd46` |
| SEQ-01 | MED | sequence-diagrams 쓰기 도식 | 의존성이 writer 세션을 열고 View 가 DTO 검증 뒤 commit, 예외는 세션 종료가 rollback(렌더·원문 둘 다) | Fixed | `ccdd874` |
| DEV-02 | LOW | development 도식 | "서비스/트랜잭션" 노드 → Service 업무 규칙 / View 의 DTO 검증 뒤 commit | Fixed | `ea2fd46` |
| TST-01 | HIGH | testing 명령 | `REDIS_HOST=… REDIS_PORT=… uv run python -m pytest -m "not mysql"`(README 실행 절과 같게) | Fixed | `ea2fd46` |
| TST-02 | LOW | testing 표 | 인증·레이트 리밋은 fakeredis 단위 테스트(`tests/core/test_rate_limiter.py` 등) | Fixed | `ea2fd46` |
| TST-03 | MED | testing | ruff format·mypy·review_gate·`-m mysql --mysql-required`·`-m e2e`·skip=실패, 나머지는 README 링크 | Fixed | `ea2fd46` |
| REQ-01 | MED | request-processing·deployment request id | 삭제. 실제 수집 항목과 로그 연결 기준(경로·메서드·시각·user_id) | Fixed | `ccdd874`, `c3d8396` |
| REQ-02 | MED | request-processing "Routed DB session" | read_only/writer 세션, routed 는 승인된 특수 경로용·기능 라우터 미사용 | Fixed | `ccdd874` |
| REQ-03 | MED | request-processing | 미들웨어 순서(예외 → UserInfo → CORS), DEBUG=true 면 다시 던짐, Redis 503 | Fixed | `ccdd874` |
| API-01 | MED | api 공통 규칙 | `/docs`·`/openapi.json` 은 DEBUG=true 만(main.py `openapi_url`·`_add_health_and_docs`) | Fixed | `c3d8396` |
| API-02 | LOW | api 공통 규칙 | 레이트 리밋은 register·login 만, PublicWrite 는 레이트 리밋을 뜻하지 않음 | Fixed | `c3d8396` |
| API-03 | LOW | api | 성공 상태 열(201/200/204), 401/403/404/409/422/429/503, `/admin` 마운트 | Fixed | `c3d8396` |
| CFG-01 | MED | configuration 설명 열 | Settings Field 설명 + 검사 규칙으로 교체, 값 잘림 제거 | Fixed | `c3d8396` |
| CFG-02 | MED | configuration | 69 필드 전수(클래스 열), `.env` 없을 때 필수 8개, ADMIN 레거시 거부 | Fixed | `c3d8396` |
| CFG-03 | LOW | configuration 도식 | import 시점 검사 → RuntimeError, staging/production 전용 검사 | Fixed | `c3d8396` |
| GS-01 | MED | getting-started | 설정 검사는 config import 시점, lifespan 은 Redis·(DEBUG 시) DB | Fixed | `c3d8396` |
| GS-02 | MED | getting-started | 비밀 키 3종·MYSQL_PASSWORD(예시 값이면 기동 거부), Redis 6.2+, DEBUG=true 면 MySQL, 슈퍼유저 생성 | Fixed | `c3d8396` |
| GS-03 | LOW | getting-started 도식 | DB 접속·테이블 생성은 DEBUG 만, 버전 확인은 Redis, /ready 는 별도 | Fixed | `c3d8396` |
| GS-04 | LOW(일부) | getting-started | /ready 는 SELECT 1·PING 만 — 스키마 불일치는 요청 시점 500 | Fixed | `c3d8396` |
| ARC-01 | MED | architecture | 모델·Celery 태스크 디렉터리 규칙 자동 탐색(`models_registry`) | Fixed | `ccdd874` |
| ARC-02 | LOW | architecture | 기능 간 import 금지(auth→user 만), `tests/core/test_layering.py` | Fixed | `ccdd874` |
| ARC-03 | LOW | architecture·sequence-diagrams | main.py 중복 링크 → main.py·features/admin.py·resources.py | Fixed | `ccdd874` |
| ARC-04 | LOW(일부) | index·architecture·development | "명시적 조립형" 삭제 → "main.py 에서 include_router 로 조립" | Fixed | `ccdd874`, `ea2fd46`, `370b51b` |
| AUT-01 | LOW | authentication·features/auth | refresh·logout 레이트 리밋 없음, 로그인 성공 시 IP+사용자명 카운터만 초기화 | Fixed | `ccdd874`, `ea2fd46` |
| AUT-02 | MED | authentication | su 는 발급 시점 값(만료 15분까지), 회전 시 폐기 family·비활성 사용자 거부, /me 만 DB 재조회 | Fixed | `ccdd874` |
| FAU-01 | LOW | features/auth 도식 | AuthService → RefreshTokenStore 직접 | Fixed | `ea2fd46` |
| FRP-01 | MED | features/reports | POST snapshots(DELETE+INSERT, 커밋 1회) 쓰기 경로 | Fixed | `ea2fd46` |
| FHM-01 | MED | features/home | tasks.py(beat 03:30) 보존 삭제·통계, ACCESS_LOG_RETENTION_DAYS, 소스 목록 | Fixed | `ea2fd46` |
| FIX-01 | MED | features/index | "공개 서비스 계약/통합 계층" 삭제 → 기능 간 import 금지(auth→user) | Fixed | `ea2fd46` |
| FIX-02 | MED | features/index | app/features/admin.py 의 ADMIN_VIEWS 명시 import 등록 | Fixed | `ea2fd46` |
| DEV-01 | MED | development | include_router 를 AccessPolicyGuard().verify 위에, 선언 없으면 기동 거부, ADMIN_VIEWS, 자동 탐색 | Fixed | `ea2fd46` |
| SEQ-02 | LOW | sequence-diagrams 기동 | worker 자원 아님 → Redis PING·버전, DEBUG create_all, drain·close·dispose | Fixed | `ccdd874` |
| SEQ-03 | LOW | sequence-diagrams 인가 | superuser 경로 토큰 실패 401, 소유권 검사는 진입 후 Service | Fixed | `ccdd874` |
| OPS-01 | LOW | deployment | URL → MYSQL_*/REDIS_* 개별 키(DSN 은 ALEMBIC_DATABASE_URL 만) | Fixed | `c3d8396` |
| OPS-02 | MED | deployment | ENV 게이트·필수 8개·Redis 6.2·종료 예산·슈퍼유저·beat. **다르게 고침:** 지적의 "Redis 장애 = 전 API 503" 은 코드와 다르다 — 503 은 Redis 를 쓰는 요청만(`get_redis` 소비처: 레이트 리밋·refresh 저장소·관리 세션·/ready), README 와 같게 씀. 처리: 지적 일부 정정 — 감독 정정 | Fixed(지적 일부 정정 — 감독 정정) | `c3d8396` |
| HUB-01 | LOW | guides/index.html | 줄 단위 서식·끝 개행, README 링크 복원, sequence-diagrams 를 새 문서(처음 읽기) 묶음으로, 19편 전부 링크 | Fixed | `370b51b`, `6195d85` |
| HUB-02 | LOW | HTML 19편 | mermaid@11.12.0 + CDN 실패 안내, CODE-VERIFIED 라벨 제거(ADR-002) | Fixed | `ccdd874`, `c3d8396`, `ea2fd46` |
| RDM-01 | LOW | README 문서 안내 | 허브 행을 "HTML 목차, 색인은 이 표가 정본" 으로 | Fixed | `370b51b` |
| RR-01 | LOW | docs-guide-review/residual-risk.md | 작업 트리 CRLF. **추가:** 생성물이 기존 행·열 이름을 고쳐 쓴 것(append-only 위반)을 main 내용으로 되돌리고 후속 기록을 덧붙임. 이번 남은 위험은 이 그룹 residual-risk 에 등록 | Fixed | `370b51b` |
| 부수-1 | LOW | .env.example | admin-auth-guide.html → workflows/admin-authentication.html | Fixed | `b241acc` |
| 부수-2 | LOW | services docstring | blog·reply·sns·user: 핸들러 커밋 / home: sink 가 background 세션에서 커밋 | Fixed | `b241acc` |

## Round 2 — 2026-10-22 · 수정본 재검수(Codex 실증 + Claude 재검수) 남은 결함

> 입력: round2 재검수 "남은 결함" 의 default 몫(D-N1~D-N8)과 가로 결함 X-1(X-2 는 D-N7 로 포함). 고치기 전에 코드 근거를 다시 열었고 9건 모두 맞았다.
> 아래 D-N8 은 Round 1 머리말("42건 모두 처리")과 CFG-02·OPS-02 의 `Fixed` 가 사실과 달랐다는 **정정 행**이다 — 위 행은 고치지 않는다(append-only).

| ID | 심각도 | 문서 | 고친 것(코드 근거) | Status | 커밋 |
|---|---|---|---|---|---|
| D-N1 | MED | configuration·getting-started·.env.example | `.env` 부재 필수 8개 검사와 ADMIN 레거시 검사도 `ENV=test` 에서 건너뜀(config.py `validate_env_source`·`validate_no_legacy_admin` 의 `env == "test"`). .env.example "모든 ENV" → "test 외 모든 ENV" | Fixed | `0f8489d` |
| D-N2 | MED | getting-started·deployment | "전체 예산 20초" → 단계별 제한 5/5/10 + 로그 flush 2, `SHUTDOWN_TOTAL_TIMEOUT_SECONDS` 는 정의만(강제 안 함), lifespan 약 22초·listener 까지 약 29초(resources.py 69-73, queue_handler `LOG_FLUSH_TIMEOUT_SECONDS`; ARCHITECTURE §8·server-lifecycle 과 같게) | Fixed | `0f8489d` |
| D-N3 | MED | api·features/user | PATCH 사용자: 비활성화=refresh+관리 세션, 강등=관리 세션만, access 는 만료까지(user_service.py `update_user`) | Fixed | `0f8489d` |
| D-N4 | LOW | features/home·features/index·허브 | "모든 요청" → `ACCESS_LOG_ENABLED` 이고 제외 경로·확장자가 아닌 요청(user_info_middleware.py `_should_skip`), 도식 렌더·원문 둘 다 | Fixed | `0f8489d` |
| D-N5 | LOW | configuration·README | "위반을 RuntimeError 하나로" → 세 검사는 순차 fail-fast, 위반 집계는 `validate_deployment_safety` 안에서만(config.py 끝 세 호출) | Fixed | `0f8489d` |
| D-N6 | LOW | tests/test_docs_guide_site.py | Mermaid 도식 페이지는 고정 URL 을 정확히 한 번(고정 삭제 변이에서 옛 검사 통과 → 새 검사 실패) | Fixed | `19bb96d` |
| D-N7 | LOW | tests/test_docs_guides.py | 상대 링크 `#조각` 이 대상 HTML id·Markdown 제목 앵커로 실재(없는 앵커 변이: 옛 통과 → 새 실패) | Fixed | `19bb96d` |
| X-1 | MED | tests/test_docs_guide_site.py | 기능별 API 표 ⊆ openapi × 접근 수준(features/user 수준 변조: 옛 통과 → 새 실패). 명세의 P-N5 지시대로 설정 표 클래스·코드 기본값 대조도 추가(MYSQL_PORT 변조: 옛 통과 → 새 실패) | Fixed | `19bb96d` |
| D-N8 | MED | 이 그룹 ledger·checklist·run-log | **정정:** Round 1 의 "42건 모두 처리"·CFG-02/OPS-02 `Fixed`·`CONVERGED` 는 사실과 달랐다 — CFG-02 는 ENV=test 생략(D-N1), OPS-02 는 종료 예산(D-N2)이 남은 일부 수정이었다. Round 2 로 닫고 기록을 덧붙임 | Fixed | 이 기록 커밋 |
