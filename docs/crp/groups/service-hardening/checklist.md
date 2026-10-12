# Checklist — service-hardening (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. 라운드 시작 시 이번 할 일을 적고, GATE 진행에 따라 체크한다. ledger 의 Fix 항목과
> 1:1 로 연결한다(하드닝은 residual-risk 로 가므로 여기 두지 않는다).

공통: 모든 Fix 는 회귀 테스트 추가 + fail-on-revert 검증을 통과해야 닫힌다. 라운드 하나 = 단계 하나.

## Round 1 — 2026-10-12 · 단계 A (CI 재현성 · DSN · 잠금 읽기 · 정렬)
- [x] 이번 요청을 design-baseline §2 에 기록 + 이전 요구 충돌 확인 (REQ-001, `orm-raw-repository` C-9 → ADR-002)
- [x] (F-001) CI `uv sync --locked` + 주석 정정 + README 갱신 — `tests/test_ci_contract.py`
- [x] (F-002) 게이트 파일 목록을 `git ls-files -z` 로 — 추적되지 않은 파일이 목록에 없다는 테스트
- [x] (F-003) DSN `URL.create` · 마스킹 · Alembic `%` · Redis 비밀번호 인코딩 — 왕복 테스트, 기존 문자열 비교를 의미 비교로
- [x] (F-004) ORM 잠금 읽기 writer 고정·read-only 거부 — 라우터 on/off 테스트
- [x] (F-005) `list()` 기본 정렬 + `created_at desc` 보조 키 — 동률 결정성·offset 페이지 비중첩 테스트
- [x] 공통 게이트 그린(ruff·format·mypy·pytest skip 0) · 요구사항 회귀 0 — 669 passed · skipped 0
- [x] run-log 갱신 · residual-risk 갱신(그룹 개설 시 R-001~R-009, 이번 라운드 추가 없음)

## Round 2 — 2026-10-12 · 단계 B (접속 로그 수집 · 오류 매핑)
- [x] (F-006) `ClientIPResolver` + `TRUSTED_PROXY_HOPS` — 홉 계수 해석은 ADR-021
- [x] (F-007) 미들웨어 예외 시 500 기록 후 재전파
- [x] (F-008) 쿼리스트링 민감 값 마스킹 + 세션 쿠키 이름을 설정에서
- [x] (F-009) 모델 컬럼 길이로 절단(home 기능 `fit_to_columns`)
- [x] (F-010) `PatchSchema` null 거부 — Update 스키마 5종 상속
- [x] (F-011) DB 오류 코드별 매핑 — `DatabaseErrorTranslator`(ORM·Raw 공통), 기능 쿼리는 `_execute`
- [x] (F-025) DB 실패 로그는 타입·코드만, 엔진 `hide_parameters=True` (검수 R-07, ADR-022)
- [x] (F-012) 리포트 날짜 범위 상한
- [x] (F-013) 4xx 로그 WARNING · 500 핸들러 `str(exc)` 는 DEBUG 전용(배포 환경은 DEBUG 거부) 확인
- [x] 공통 게이트 그린 · run-log 갱신 — 742 passed · skipped 0

## Round 3 — 2026-10-12 · 단계 C (테스트 하네스)
- [x] (F-014) 공용 세션 override 헬퍼 + 전 기능 전환(10개 파일) + read-only 쓰기 거부 회귀 + 손수 override 금지 계약
- [x] (F-015) MySQL ORM 스모크(`mysql` 마커 5건, 로컬은 `--collect-only` 로 수집만 확인 — 13건 수집)
- [x] (C3) 해당 없음 — 설정 reload·import 시점 객체 패치를 쓰는 테스트가 없다(`reload(` 0건)
- [x] 공통 게이트 그린 · run-log 갱신 — 746 passed · skipped 0

## Round 4 — 단계 D (UTC 저장)
- [ ] (F-016) `UTCDateTime` · `utc_now` · 리비전(`DATETIME(6)` + `CONVERT_TZ`) · 리포트 오프셋 · Celery `enable_utc`
- [ ] 공통 게이트 그린 · run-log 갱신

## Round 5 — 단계 E (Redis 필수 · /ready · Celery 발견)
- [ ] (F-017) `get_redis` provider + `/ready` DB·Redis 판정
- [ ] (F-018) 기능별 `tasks.py` + 자동 발견 include
- [ ] 공통 게이트 그린 · run-log 갱신

## Round 6 — 단계 F1 (인증 코어)
- [ ] 의존성 추가(`pwdlib[argon2]`, dev `fakeredis`) — 이유는 ADR-013
- [ ] (F-021) `PasswordHasher` + 레거시 bcrypt 점진 이전
- [ ] `TokenService` claim·검증 설정
- [ ] (F-019) `RefreshTokenStore` 회전·재사용 탐지·logout
- [ ] (F-020) `RateLimiter` + 라우트 의존성 + 429 `Retry-After`
- [ ] 공통 게이트 그린 · run-log 갱신

## Round 7 — 단계 F2 (인가 · 소유권 · 운영 도구)
- [ ] `Principal` · `get_current_principal` · `require_superuser` · `OwnershipPolicy`
- [ ] (F-022) blog·sns·reply·user·catalog·reports 라우트 정책
- [ ] (F-023) 접속 로그 조회 슈퍼유저 전용
- [ ] (F-024) `/users` POST 비밀번호 필수 · `scripts/create_superuser.py`
- [ ] OpenAPI 기준선 갱신 + 이유 기록(C-10) · README·ARCHITECTURE·`.env.example` 갱신
- [ ] 공통 게이트 그린 · run-log 갱신

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
