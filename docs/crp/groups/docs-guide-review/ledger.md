# Ledger — docs-guide-review (지적 원장)

> 검수 보고의 지적 ID → 처리 → 커밋. 커밋: `011efa8` HTML 안내서 3편 · `e6cbd3d` ARCHITECTURE·DEVELOPMENT · `0efc0a0` README.
> 코드 근거는 고치기 전에 다시 열어 확인했다. 지적이 틀린 것은 없었다 — 29건·누락 5건 모두 고침.

| ID | 판정·심각도 | 문서 | 고친 것(코드 근거) | Status | 커밋 |
|---|---|---|---|---|---|
| F01 | OUTDATED·HIGH | feature-development #security-tests | 명령에 `redis-test` 기동 + `REDIS_HOST`·`REDIS_PORT` (`test_uvicorn_lifecycle.require_redis` 의 `pytest.fail`) | Fixed | `011efa8` |
| F02 | OUTDATED·HIGH | DEVELOPMENT §12.3 | 커버리지 명령에 같은 전제(CI gate job 과 같은 명령) | Fixed | `e6cbd3d` |
| F03 | WRONG·MED | server-lifecycle #setting-map | Redis 소비자에 `/ready`·관리 세션·관리 로그인 레이트 리밋(`features/admin.py _app_redis`) | Fixed | `011efa8`, README `0efc0a0` |
| F04 | WRONG·MED | server-lifecycle #health | `/ready` = DB `SELECT 1` + Redis `PING` 동시, 하나라도 실패 503(`readiness_check`) | Fixed | `011efa8` |
| F05 | OUTDATED·MED | server-lifecycle #health·#setting-map, feature-development #mvc·#security-tests | 서명 세션 쿠키 → Redis 서버 세션(`admin_session.py`) | Fixed | `011efa8` |
| F06 | WRONG·MED | server-lifecycle #app-assembly, ARCH §3.1 | 가장 바깥 = `unhandled_exception_middleware`, 그 안 UserInfo → CORS | Fixed | `011efa8`, `e6cbd3d` |
| F07 | WRONG·MED | server-lifecycle #worker-migrations | Celery include = `iter_task_modules()` 기능별 자동 발견 | Fixed | `011efa8` |
| F08 | WRONG·MED | feature-development #read-update | DB 오류 변환 표(1062→409, 1048·1364·1452→422, 1451→409, 그 밖 500 — `DatabaseErrorTranslator`) | Fixed | `011efa8` |
| F09 | OUTDATED·MED | feature-development #product | PATCH 명시 null → `PatchSchema` 422 | Fixed | `011efa8` |
| F10 | OUTDATED·MED | ARCH §14 | revision 체인 끝에 head `c9e1a3b5d7f0` | Fixed | `e6cbd3d` |
| F11 | OUTDATED·MED | DEVELOPMENT §5.3 | `list_active` 조각: `self._execute` + `Product.id.desc()` | Fixed | `e6cbd3d` |
| F12 | INCONSISTENT·LOW | server-lifecycle #settings, ARCH §1.1·§6.1 | 설정 클래스 12/12/10 → 9 | Fixed | `011efa8`, `e6cbd3d` |
| F13 | WRONG·LOW | server-lifecycle #registration | 23/38 → 24/39(`app.openapi()` 실측) | Fixed | `011efa8` |
| F14 | OUTDATED·LOW | server-lifecycle #log-sinks | 파일 핸들러는 설정 로드 직후 `entry_process(sys.argv[0])` | Fixed | `011efa8` |
| F15 | OUTDATED·LOW | server-lifecycle #execution | CLI 경로도 같은 포맷, 차이는 SIGTERM 경로뿐 | Fixed | `011efa8`, README `0efc0a0` |
| F16 | MISSING·LOW | server-lifecycle #app-assembly, ARCH §1.3 | Redis 503 처리기·예외 미들웨어·422 후처리·`AccessPolicyGuard` | Fixed | `011efa8`, `e6cbd3d` |
| F17 | MISSING·LOW | server-lifecycle #health | 오류 표에 기동 뒤 Redis 연결 오류 → 503 | Fixed | `011efa8` |
| F18 | OUTDATED·LOW | ARCH §1.1·§15, README 특징 | 파일 로그 없음 → `LOG_FILE_ENABLED` 프로세스별 파일 | Fixed | `e6cbd3d`, `0efc0a0` |
| F19 | MISSING·LOW | ARCH §1.1 | 트리에 `compose.e2e.yaml`·`tests/e2e` | Fixed | `e6cbd3d` |
| F20 | MISSING·LOW | ARCH §6.2(같은 사실: server-lifecycle JWTSettings 행) | `jwt_settings` 소비처에 관리 로그인 레이트 리밋(`AdminAuthBackend.login`) | Fixed | `e6cbd3d`, `011efa8` |
| F21 | WRONG·LOW | admin-authentication #overview | `SESSION_SECRET_KEY` 소비처에 로그 마스킹(`LOG_SECRET_SETTINGS`) | Fixed | `011efa8` |
| F22 | OUTDATED·LOW | admin-authentication 머리 | 기준 브랜치 → main `6eff7a2` | Fixed | `011efa8` |
| F23 | OUTDATED·LOW | HTML 머리 | 기준일·최종 갱신 2026-10-21, 기준 main `6eff7a2`(3편 모두) | Fixed | `011efa8` |
| F24 | WRONG·LOW | feature-development #checklist | `server-lifecycle-guide.html` → `server-lifecycle.html` | Fixed | `011efa8` |
| F25 | UNCLEAR·LOW | feature-development #security-tests(같은 사실: README §0) | 미지정 → 실패, 지정했는데 불통 → skip | Fixed | `011efa8`, `0efc0a0` |
| F26 | OUTDATED·LOW | feature-development #async-background | `get_redis` 주입 + 전역 503 처리기 | Fixed | `011efa8` |
| F27 | UNCLEAR·LOW | ARCH §3.3·§4.3·§12 | "e2e-policy-2 결정 N" → integration-e2e ADR-012·016·013·014·015 | Fixed | `e6cbd3d` |
| F28 | UNCLEAR·LOW | ARCH §16 | 변경 이력을 최신순으로(같은 날짜는 기존 순서) + 이번 한 줄 | Fixed | `e6cbd3d` |
| F29 | MISSING·LOW | admin-authentication #architecture | 메인 앱 미들웨어 목록·구성도에 예외 미들웨어 | Fixed | `011efa8` |
| M1 | 누락 | server-lifecycle #redis | 기동 뒤 Redis 장애: API 503·관리 화면 503·`/ready` 503 | Fixed | `011efa8` |
| M2 | 누락 | feature-development #di | replica 연결 오류 → primary 1회 재실행 후 고정 | Fixed | `011efa8` |
| M3 | 누락 | feature-development #security-tests, server-lifecycle #operations | e2e 실행·CI 세 job·새 API 시 `SPECS`·라우트 인벤토리 갱신 | Fixed | `011efa8` |
| M4 | 누락 | server-lifecycle #app-assembly | `AccessPolicyGuard`·422 후처리(F16 과 함께) | Fixed | `011efa8` |
| M5 | 누락 | ARCH §1.1 | e2e 파일(F19 와 함께) | Fixed | `e6cbd3d` |
