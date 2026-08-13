# Ledger — orm-raw-repository (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.
>
> **Open 인 Fix 가 0건이어야 다음 Phase 로 넘어간다** (ADR-006).

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | HIGH | INV-9 / AR-009 — drain timeout 후 pending 은 cancel + **await** 되어야 한다 | Fix | Fixed | `resources.DRAIN_WAIT_RATIO` + `test_cancelled_task_cleanup_survives_the_outer_timeout` | `_drain_background_tasks` 가 `drain()` 내부 timeout 과 바깥 `asyncio.timeout` 에 **같은 5초**를 줘, drain 이 pending 을 취소하고 gather 로 회수하려는 순간 바깥 guard 가 끊었다. 태스크의 `finally`(세션 rollback/close)가 실행되지 못한 채 DB dispose 로 넘어감 |
| F-002 | LOW | 기존 계약 — 환경변수는 `config.py` 만 직접 읽는다 | Fix | Fixed | `scripts/review_gate.py` (DEBUG setdefault 제거) | 검수 스크립트가 subprocess 스니펫에서 `os.environ` 을 직접 만져 `test_only_config_reads_environment_directly` 를 깼다. DEBUG 는 `app.openapi()` 결과에 영향이 없어 제거로 해결 |
| F-003 | CRIT | 작업 절차 — 일괄 치환이 대상 외 파일을 훼손하지 않을 것 | Fix | Fixed | `git checkout` 복구 (커밋 전 발견) | PowerShell 루프에서 `Get-Content -Raw` 가 빈 파일에 `$null` 을 돌려주자 `$t.Replace()` 가 **비종료 오류**를 냈고, `$n` 이 이전 반복 값을 유지해 빈 파일 6개(`*/tests/test_db.py` 5개 + `home/tests/test_endpoint.py`)에 다른 파일 내용이 기록됐다. 전량 복구 후 **일괄 치환은 Python 스크립트로만** 수행하도록 절차 변경 |

| F-004 | HIGH | ORM-REP-003 — Repository 는 호출자가 전달한 dict 를 변경해서는 안 된다 | Fix | Fixed | `repository_base.create` + `test_create_does_not_mutate_caller_dict` | `create()`/`bulk_create()` 가 `data["id"] = str(uuid4())` 로 **호출자의 dict 를 직접 변조**했다. Service 가 같은 dict 를 재사용하면 조용히 오염된다. id 기본값은 모델 Mixin 의 `default` 가 만들도록 이관 |
| F-005 | HIGH | ORM-REP-006 — 모든 create/update/delete/bulk 경로가 동일한 예외 변환 정책을 쓴다 | Fix | Fixed | `_translated_errors()` + 파라미터화 회귀 6건 | `bulk_update`·`update_by`·`bulk_delete`·`delete_by`·`get_all`·`count`·`exists` 에는 예외 변환이 **전혀 없어** 드라이버 예외가 그대로 호출자에게 도달했다. 호출자가 계층마다 다른 예외를 처리해야 했음 |
| F-006 | MED | NFR-001 — 사용자 오류 응답에 SQL 파라미터를 싣지 않는다 | Fix | Fixed | `_translated_errors()` detail 에서 원문 제거 + `test_error_detail_does_not_leak_sql_parameters` | 예외 변환이 `detail={"error": str(e.orig)}` 로 드라이버 원문을 응답에 실었다. 무결성 위반 메시지에는 위반한 **값 자체**(중복된 이메일 등)가 들어 있어 그대로 유출됐다. 원문은 서버 로그로만 |
| F-007 | MED | 테스트 격리 — 테스트 모델이 공유 `Base.metadata` 를 오염시키면 안 된다 | Fix | Fixed | `tests/core/test_repository_base.py` 의 `_TestBase` | 새 Repository 테스트가 공유 Base 에 `repo_base_widgets` 를 등록해 스키마 스냅샷·마이그레이션 정합성 테스트가 유령 테이블을 봤다. 격리된 DeclarativeBase 로 분리(Mixin 은 그대로 재사용) |

| F-008 | **CRIT** | NFR-001 — 로그에 전체 SQL 파라미터를 기록하지 않는다 | Fix | Fixed | `SqlNoiseFilter` + `LOG_SQL_ECHO_ENABLED` + `tests/core/test_sql_logging_leak.py` | 프로젝트 기본값 `DEBUG=true` → 유효 로그 레벨 DEBUG → **SQLAlchemy·드라이버가 실행 SQL 과 바인딩된 값을 그대로 로그로 내보냈다**(실측 확인). 값에는 비밀번호 해시·토큰·검색어가 들어 있고 로그는 외부 collector 로 흘러간다. ADR-019(앱별 로거 미등록)를 지키기 위해 `loggers` 키 대신 queue 핸들러 **필터**로 차단. WARNING 이상은 통과시켜 장애는 계속 보인다 |
| F-009 | HIGH | 로깅 가용성 — 인프로세스 Alembic 실행이 애플리케이션 로깅을 죽이면 안 된다 | Fix | Fixed | `migrations/env.py` `fileConfig(..., disable_existing_loggers=False)` | `fileConfig` 기본값이 기존 로거를 **전부 비활성화**한다. 같은 프로세스에서 alembic 을 돌리면(기동 시 마이그레이션·테스트 하네스) 그 순간부터 앱 로그가 조용히 사라진다. 테스트에서 `test_migration_chain` 이후 Raw Repository 로그가 통째로 사라지는 것으로 발견 |
| F-010 | LOW | 검수 게이트 정확도 — INV-5 판정이 오탐이면 안 된다 | Fix | Fixed | `scripts/review_gate.py` AST 기반 base 검사 | 게이트가 문자열 검색으로 INV-5 를 판정해, "BaseRepository 를 상속하지 않는다"라고 적은 **docstring 까지 위반으로 잡았다**. 실제 클래스 정의의 base 목록만 보도록 수정 |

| F-011 | **HIGH** | RAW-REP-007 / TX-002 — read-only 세션에서 Raw DML 이 차단되고, 쓰기는 primary 로 간다 | Fix | Fixed | `router._text_is_write()` + `tests/core/test_router_raw_dml.py` | `_is_write()` 가 `isinstance(clause, UpdateBase)` 만 봐서 **`text("DELETE ...")` 를 읽기로 판정**했다. 결과: ①read-only 세션의 쓰기 차단이 뚫린다 ②복제 활성 시 **UPDATE 가 replica 로 나간다**(더 위험). 선두 키워드 판별 + `SELECT ... FOR UPDATE` 감지로 수정. CTE 로 감싼 DML 은 여전히 오판 — `ponytail:` 주석으로 한계 명시 |
| F-012 | MED | 통합 환경 — 테스트가 의도한 DB 에 붙어야 한다 | Fix | Fixed | `compose.test.yaml` 포트 3307 → 3308 | Windows 의 `127.0.0.1:3307` 을 **IDE(VS Code)의 포트 포워딩이 선점**하고 있어, 접속이 조용히 다른 MySQL 로 가서 "Access denied" 로만 보였다. `Get-NetTCPConnection` 으로 점유 프로세스를 확인해 원인 특정. 충돌 없는 3308 로 이전하고 확인 방법을 주석에 남김 |
| F-013 | MED | 통합 환경 — MySQL 8.4 접속 가능 | Fix | Fixed | `pyproject.toml` `cryptography>=43.0.0` | MySQL 8.4 기본 인증(`caching_sha2_password`)에는 PyMySQL/aiomysql 이 `cryptography` 를 필요로 한다. 없으면 접속 자체가 실패 |
| F-014 | LOW | 통합 테스트 격리 — 스키마 초기화가 alembic 상태와 어긋나면 안 된다 | Fix | Fixed | `tests/integration/conftest.py` `drop_all_tables_sync()` + `mysql_empty_schema` | metadata 기준 초기화는 `alembic_version` 을 남겨, alembic 이 "base 상태"로 오인하고 이미 있는 테이블을 다시 만들다 1050 으로 깨졌다. 실제 존재하는 테이블 전부를 지우고, migration 테스트는 빈 스키마 fixture 를 쓰도록 분리 |

| F-015 | MED | DOC-003 — 공개 스키마는 문서에서 식별 가능한 이름을 가진다 | Fix | Fixed | `auth_schema.AuthUserResponse` + `test_schema_names_are_not_module_qualified` | auth 와 user 양쪽에 `UserResponse` 가 있어 FastAPI 가 충돌을 피하려고 `app__features__auth__schemas__auth_schema__UserResponse` 라는 키를 만들었다. 이 이름이 **Scalar 문서와 생성 SDK 에 그대로 노출**된다. auth 쪽을 `AuthUserResponse` 로 개명하고, 스키마 키에 `__` 가 나타나면 실패하는 규칙을 추가 |
| F-016 | MED | 테스트 결정성 — 검증 결과가 주변 환경에 좌우되면 안 된다 | Fix | Fixed | `tests/core/test_db_router_env.py` `PYTHONIOENCODING=utf-8` | 자식 프로세스의 stderr 를 utf-8 로 디코딩하는데 자식은 Windows 콘솔 코드페이지(cp949)로 썼다. 한글이 U+FFFD 로 바뀌어 "오류 메시지에 이 단어가 있는가" 검증이 조용히 실패했다. ASCII 를 보는 형제 케이스는 통과해서 더 늦게 드러났다. 자식의 stdio 인코딩을 명시해 환경 의존을 제거 |
| F-017 | **HIGH** | ADR-006 — 게이트는 결함을 **보고**해야 한다 | Fix | Fixed | `scripts/review_gate.py` stdout UTF-8 재설정 | 게이트가 실패 상세를 출력하는 순간 cp949 로 em dash 를 못 써 `UnicodeEncodeError` 로 **죽었다**. 전건 통과일 때만 정상 종료하는 게이트여서, 실패를 "게이트가 깨졌다"로 오인할 수 있었다. 검수 장치가 초록일 때만 동작하면 검수가 아니다. 실제로 이번에 mypy 3건이 이 크래시에 가려져 있었다 |

## 검수 라운드 기록

| 라운드 | 시점 | 범위 | 게이트 결과 | 신규 finding |
|---|---|---|---|---|
| R-1 | 2026-08-13 | Phase 0~1 소급 | 전건 통과 (240 tests) | F-001, F-002, F-003 |
| R-2 | 2026-08-13 | Phase 2 (모델 Mixin) | 전건 통과 (253 tests) | 없음 — schema diff 0 을 스냅샷으로 증명 |
| R-3 | 2026-08-13 | Phase 3 (ORM Repository) | 전건 통과 (274 tests) | F-004, F-005, F-006, F-007 |
| R-4 | 2026-08-13 | Phase 4 (Raw Base) | 전건 통과 (308 tests) | F-008(CRIT), F-009, F-010 |
| R-5 | 2026-08-13 | Phase 5 (시나리오 2종 + MySQL 8.4) | 전건 통과 (364 tests, MySQL 통합 6건 실제 실행) | F-011(HIGH), F-012, F-013, F-014 |
| R-6 | 2026-08-13 | Phase 6 (Scalar/OpenAPI) | 전건 통과 (373 tests) | F-015, F-016, F-017(HIGH) |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
