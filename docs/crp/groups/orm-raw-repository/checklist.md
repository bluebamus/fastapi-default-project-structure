# Checklist — orm-raw-repository (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가
> 아니다. 라운드 시작 시 이번 할 일을 적고, GATE 진행에 따라 체크한다. ledger 의 Fix 항목과
> 1:1 로 연결한다(하드닝은 residual-risk 로 가므로 여기 두지 않는다).

공통: 모든 Fix 는 회귀 테스트 추가 + fail-on-revert 검증을 통과해야 닫힌다.
타깃 플랫폼은 Windows(개발)와 Linux(CI) 둘 다이며, 한쪽에서만 재현되는 결함이 실제로 있었다
(F-016 · 그리고 그룹 개설 직전의 cp949 디코딩 실패 `1a07cd2`).

## Round 1 — 2026-08-13 · Phase 0~1 (기준선 + 런타임)
- [x] 이번 요청을 design-baseline §2 에 기록 + 이전 요구 충돌 확인 (REQ-001~003, C-1~C-9)
- [x] Phase 0 기준선 고정 — `baseline/openapi.json` · `baseline/survey.txt` (MIG-001)
- [x] 검수 게이트 상설화 — `scripts/review_gate.py` (ADR-006)
- [x] (F-001 HIGH) 드레인 취소 회수가 바깥 timeout 에 잘림 — `DRAIN_WAIT_RATIO` +
      실제 `BackgroundTaskRunner` 로 정리 완료를 증명하는 테스트
- [x] (F-002 LOW) 게이트가 subprocess 에서 환경변수를 직접 조작 — 제거
- [x] (F-003 CRIT) 일괄 치환이 빈 파일 6개를 훼손 — 커밋 전 복구 + **절차 변경**
      (일괄 치환은 Python 스크립트로만)
- [x] GATE 3 인수기준 전부 그린 (240 tests)
- [x] 요구사항 회귀 0 — 공개 API 경로·응답 불변 확인
- [x] run-log 심각도 추세 갱신 + 수렴 판정 기록
- [x] residual-risk 갱신 — 이번 라운드 신규 수용 없음

## Round 2 — 2026-08-13 · Phase 2 (모델 Mixin)
- [x] 리팩터 **이전에** 컬럼 순서 포함 스키마 지문 스냅샷 확보 (안전망 먼저)
- [x] Mixin 조합으로 재구성 — `UUIDPrimaryKeyMixin` · `CreatedAtMixin` · `UpdatedAtMixin`
- [x] GATE 3 인수기준 전부 그린 (253 tests) — **schema diff 0 을 스냅샷으로 증명**
- [x] 요구사항 회귀 0 · run-log 갱신 · residual-risk 갱신(신규 없음)
- 신규 Fix 0 건 — ledger 연결 항목 없음

## Round 3 — 2026-08-13 · Phase 3 (ORM Repository)
- [x] Base 공개 계약을 최소 CRUD 8개로 축소 (823→185줄, Phase 0 의 사용처 0건 근거)
- [x] (F-004 HIGH) `create()` 가 호출자 dict 를 변조 — id 기본값을 모델 Mixin 으로 이관
- [x] (F-005 HIGH) 7개 경로에 예외 변환이 아예 없음 — `_translated_errors()` 로 통일
- [x] (F-006 MED) 오류 응답 detail 에 드라이버 원문(=위반한 값) 노출 — 원문은 서버 로그로만
- [x] (F-007 MED) 테스트 모델이 공유 `Base.metadata` 오염 — 격리된 `_TestBase`
- [x] GATE 3 인수기준 전부 그린 (274 tests)
- [x] 요구사항 회귀 0 · run-log 갱신 · residual-risk 갱신(신규 없음)

## Round 4 — 2026-08-13 · Phase 4 (Raw Base)
- [x] `RawCRUDBase` / `RawRepositoryBase` 신설 — ORM Base 와 상속 관계 없음(INV-5)
- [x] (F-008 CRIT) SQL 과 **바인딩된 값**이 로그로 유출 — `SqlNoiseFilter` +
      `LOG_SQL_ECHO_ENABLED=false`. 실측 프로브로 유출 확인 → 수정 후 재확인
- [x] (F-009 HIGH) `fileConfig` 기본값이 앱 로거를 전부 비활성화 —
      `disable_existing_loggers=False`
- [x] (F-010 LOW) 게이트의 INV-5 문자열 판정이 docstring 오탐 — AST base 검사로 교체
- [x] GATE 3 인수기준 전부 그린 (308 tests)
- [x] 요구사항 회귀 0 · run-log 갱신
- [x] residual-risk — R-002(Raw 방언 이식성 비보장) 후보 인지

## Round 5 — 2026-08-13 · Phase 5 (시나리오 2종 + MySQL 8.4)
- [x] `catalog`(ORM) · `reports`(Raw) 참조 예제 + Alembic revision 2건(upgrade/downgrade)
- [x] MySQL 8.4 전용 컨테이너 — `compose.test.yaml`(포트 3308, tmpfs)
- [x] (F-011 HIGH) `text("DELETE ...")` 를 읽기로 판정 — read-only 차단이 뚫리고
      복제 활성 시 **UPDATE 가 replica 로** 나감. 선두 키워드 판별 + `FOR UPDATE` 감지
- [x] (F-012 MED) IDE 포트 포워딩이 3307 선점 — 3308 로 이전 + 확인 방법 주석화
- [x] (F-013 MED) MySQL 8.4 `caching_sha2_password` 에 `cryptography` 필요
- [x] (F-014 LOW) 스키마 초기화가 `alembic_version` 잔류 — `drop_all_tables_sync()` +
      빈 스키마 fixture 분리
- [x] GATE 3 인수기준 전부 그린 (364 tests, **MySQL 통합 6건 실제 실행**)
- [x] 요구사항 회귀 0 · run-log 갱신
- [x] residual-risk — R-001(CTE DML 오판) 수용, F-011 수정의 알려진 상한

## Round 6 — 2026-08-13 · Phase 6 (Scalar/OpenAPI)
- [x] 문서 계약을 **규칙 9개**로 고정 — `tests/test_openapi_contract.py` (DOC-001·003·004·005)
- [x] 9개 규칙 전부 **fail-on-revert 검증** (결함 상태 주입 → 해당 규칙만 실패)
- [x] (F-015 MED) 스키마 이름이 모듈 경로로 뭉개짐 — `AuthUserResponse` 로 개명 +
      스키마 키의 `__` 금지 규칙
- [x] (F-016 MED) 자식 프로세스 stderr 인코딩 미고정 — 결과가 콘솔 코드페이지에 좌우됨
- [x] (F-017 HIGH) **게이트가 실패를 보고하는 순간 죽음** — stdout UTF-8 재설정.
      이 크래시에 mypy 3건이 가려져 있었음
- [x] 태그 메타데이터 정합 — `Auth` 추가 · `Analytics` 제거 · 구현 완료 기능의 '예정' 문구 제거
- [x] GATE 3 인수기준 전부 그린 (373 tests)
- [x] 요구사항 회귀 0 · run-log 갱신 · residual-risk 갱신(신규 없음)

## Round 7 — 2026-08-14 · Phase 7 (문서 + 호환 이름 제거)
- [x] README·ARCHITECTURE·QUICKSTART·workflow-guide 를 실제 코드와 대조
- [x] 문서가 참조하는 파일 경로 **전수 기계 검사** (실재 확인)
- [x] (F-018 MED) 따라 하면 깨지는 문서 — 제거된 `get_all_with()` 안내, 옛 Repository
      메서드 목록, deprecated 세션 이름 23곳, **존재하지 않는 환경변수 8개**
- [x] MIG-002 단계 9 — 세션 별칭 5개 제거(사용처 0건 확인 후)
- [x] MIG-002 단계 9 — Repository 별칭 4개 제거(**호출부 16곳 전환 후**)
- [x] 명명 계약 테스트를 "같은 객체인가" → **"되살아나지 않았는가"** 로 전환
- [x] 롤백 로그 라벨이 제거된 함수명을 가리키던 것 정정
- [x] GATE 3 인수기준 전부 그린 (373 tests, MySQL 통합 6건 실제 실행)
- [x] 요구사항 회귀 0 — design-baseline Active 요구·불가침 제약(C-1~C-9) 위반 없음.
      **C-7 확인**: 3306 의 공유 `percona-mysql-8.4` 인스턴스를 건드리지 않았다
- [x] run-log 심각도 추세 갱신 + 최종 수렴 판정
- [x] residual-risk 갱신 — R-001~R-006 수용 + **검사하지 않은 것** 5항목 명시

## Round 8 — 2026-08-19 · 완료 여부 재확인 (독립 검증)
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-004) + 이전 요구 충돌 확인
- [x] 문서 주장 ↔ 실제 코드 대조 — 산출물 10종 실재 · ledger 인용 회귀 테스트 실재 확인
- [x] 게이트 전건 통과 + **373 tests, 0 skipped** (MySQL 8.4 컨테이너 기동 후 통합 6건 실행)
- [x] (F-019 MED) charter·ADR-002 가 옛 포트 3307 — 실제는 3308. `compose.test.yaml` 은
      자기모순. ADR-002 를 덮어쓰지 않고 **ADR-008 로 supersede**
- [x] (F-020 LOW) 인용 커밋 해시 **12건 전부 HEAD 에서 도달 불가**(author rewrite) — subject
      기준 재매핑. 일괄 치환은 F-003 절차대로 Python 스크립트로만
- [x] 재발 방지 — 게이트 검사 7(포트 단일 출처)·8(인용 해시 도달성) 추가 (ADR-009)
- [x] 두 검사 **fail-on-revert 검증** (결함 주입 → 해당 검사만 실패, 나머지 그린)
- [x] 요구사항 회귀 0 — C-1~C-9 위반 없음. **C-7 확인**: 3306 공유 인스턴스 무접촉,
      기동한 것은 3308 전용 컨테이너뿐
- [x] run-log 심각도 추세 갱신 + 수렴 판정
- [x] residual-risk 갱신 — 이번 라운드 신규 수용 없음

## Round 9 — 2026-08-20 · REQ-005 (Raw 쓰기 참조 예제) + 중단 세션 복구
- [x] 중단된 세션의 미커밋 변경 18파일 + 신규 1파일을 전수 확인 — 무엇을 하려던 작업인지 역추론
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-005). **요청 원문은 유실**됐으므로 그 사실을 명시하고
      도출 근거(코드·주석)를 함께 적었다
- [x] ADR-010~014 확정 — 공개 API 확대 · 표준 SQL 재적재 · 자연키 · allowlist 소유 계층 · 요구 ID 검사
- [x] C-1~C-9 위반 없음 확인. **C-2**: 커밋은 View 본문 1회(Repository·Dependency 0회, 게이트 INV-2 그린).
      **C-3**: 정렬 식별자는 allowlist 통과분만 SQL 에 들어간다. **C-5**: 별칭 제거 전 사용처 0건 실측.
      **C-7**: 3306 공유 인스턴스 무접촉 — 기동한 것은 3308 전용 컨테이너뿐
- [x] (F-021 LOW) `CRUDBase.session`·`BaseService.session` deprecated 별칭 2개가 사용처 0건인 채 잔존 —
      제거 + 회귀 테스트를 **클래스 속성까지** 보도록 확장
- [x] (F-022 MED) 코드가 존재하지 않는 `SCN-RAW-003` 을 3곳에서 인용 + 범위 확대 미등록 —
      REQ-005·ADR-010 으로 정식화하고 게이트 검사 9 추가
- [x] (F-023 LOW) 검사 9 가 드러낸 pre-CRP ID 3건 — **Accept-out-of-scope** → residual-risk R-007
- [x] 검사 9 **fail-on-revert 검증** (선언되지 않은 시나리오 ID 를 코드에 주입 → 검사 9 만 그 파일을 지목해 실패, 복구 후 그린)
- [x] 게이트 전건 통과 — 검사 **9종**, **391 tests** (단위 383 + MySQL 통합 8), 0 failed
- [x] MySQL 8.4 통합 **8건 실제 실행** (컨테이너 재기동 후 — 이전 라운드 6건에서 신규 2건 증가)
- [x] charter 갱신 — 인벤토리·인수기준. **§1 기준선 실측(2026-08-13)은 착수 시점 값이라 보존**
- [x] ledger·run-log·residual-risk 갱신

## Round 10 — 2026-08-20 · 잔여 작업 확인 (charter 인수기준 ↔ 수렴 선언 대조)
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-006) + ADR-015 확정
- [x] charter §3 12칸이 **전부 열린 채** 다른 세 문서가 GATE 3 통과를 선언하고 있음을 확인 (F-024)
- [x] 12칸의 근거가 실재하는지 **칸마다 실측** — 표시만 바꾸지 않는다(F-021 의 실패를 반복하지 않는다)
- [x] (F-025 HIGH) 실측 결과 **INV-10 칸은 근거가 존재한 적이 없었다** — "전 path operation async 검사"도
      "금지 동기 I/O 정적 검사"도 저장소에 없었다. 아홉 라운드가 이 칸을 근거 없이 통과 선언했다
- [x] 코드 실측 — path operation **36개 전부 `async def`**, 요청 경로 블로킹 호출 **0건**.
      결함은 코드가 아니라 **방어선의 부재**였다
- [x] 게이트 검사 10 신설 (`check_async_path_operations`) — INV-10 을 AST 로 상설 검사
- [x] 게이트 검사 11 신설 (`check_charter_criteria_closed`, ADR-015) — 열린 칸 + 수렴 선언 동시 존재 시 실패
- [x] 두 검사 **fail-on-revert 검증** — 검사 11 은 도입 직후 실제로 F-024 를 지목해 빨개졌고(그 상태가
      곧 결함 주입이다), 12칸을 닫자 그린이 됐다. 검사 10 은 36건을 세어 보고한다(0건이면 죽은 검사다)
- [x] charter §3 12칸을 **근거와 함께** 닫음 (v0.4)
- [x] 게이트 전건 통과 — 검사 **11종**, **391 tests**, MySQL 통합 8건 실제 실행
- [x] 요구사항 회귀 0 — C-1~C-9 위반 없음. **C-7 확인**: 3306 공유 인스턴스 무접촉

## Round 11 — 2026-08-25 · REQ-007 (lifespan 종료 조립 리팩터)
- [x] 이번 요청을 design-baseline §2 에 기록 (REQ-007) + ADR-016 확정
- [x] 상위 명세 대조 — **AR-008 수용 기준이 `try/finally` 를 첫 번째 허용 형태로 명시**하므로
      요구 위반이 아님을 확인. 이탈은 development-plan §9.5 · workflow-guide §11 의 *구현 예시* 뿐
- [x] `manage_application_resources()` 를 평문 `try/finally` 로 전환 — 종료 순서가 코드 순서와
      일치하게 되어 `# 3번째로 실행` 주석 3줄이 사라짐
- [x] 잃는 보장이 없음을 확인 — 실패 격리는 ExitStack 이 아니라 `_run_cleanup()` 이 제공하고,
      콜백 3개가 획득 **이전에** 등록돼 있어 부분 정리는 애초에 작동한 적이 없다
- [x] (F-026 LOW) `"[shutdown] ... 해제 완료"` 로그가 **한 번도 출력된 적 없음** — listener 를
      멈춘 뒤에 찍고 있었다. 마지막 로그를 listener stop **앞**으로 이동
- [x] 문서 드리프트 정리 — `AsyncExitStack` import 제거, 모듈 독스트링·`ARCHITECTURE.md` §4.2 ·
      `workflow-guide.md` §11 을 실제 구조로 정정 (F-018 재발 방지)
- [x] `tests/core/test_resources.py` **13건 전건 통과** — 종료 순서·startup 실패 cleanup·
      재진입 누수·timeout 예산 전부 그린 (테스트는 **수정하지 않았다** — 계약이 안 바뀌었다는 증거)
- [x] 실제 `main.app` 기동→종료 **실측** — 리팩터 전후로 drain → dispose(`ALL DONE`) → listener stop
      순서 동일, `app.state.resources = None`. F-026 은 이 대조로 부재→출현을 눈으로 확인
- [x] 게이트 전건 통과 — 검사 **11종**, **391 tests**, MySQL 통합 8건 실제 실행
      (첫 실행은 `383 passed, 8 skipped` 였다 — 컨테이너를 올리고 재실행해 skipped 0 확인)
- [x] (F-027 LOW) 이번 라운드의 **문서 편집 자체가 불완전**했다 — ①스크립트 앵커가 여러 줄 bullet 의
      첫 줄만 잡아 절차 관찰 문장이 두 동강 남 ②실측 전 하한값이 ledger·checklist 에 잔류해 문서 간 모순.
      커밋 전 전수 점검으로 발견·복구. 게이트는 이 둘 중 어느 것도 잡지 않는다
- [x] 편집 파일 10종 **전수 무결성 점검** — UTF-8 디코딩·U+FFFD 0건·끝줄 개행·`git diff` 삽입 지점 육안 확인
- [x] 요구사항 회귀 0 — C-1~C-9 위반 없음. **C-6 확인**: shutdown 에서 table drop 없음.
      공개 API 경로·응답 스키마 불변(INV-11 그린)

---

## Round 12 — 2026-08-27 · REQ-010 (자원 수명주기 신뢰성) — **진행 중**

트리거: 전 라운드 산출물에 대한 외부 검토 계획서(v1)를 받고 그 타당성 검수를 요청받았다.
검수 기준은 **코드의 가용성** — "일반적으로 사용하는 방법" 으로 설계·구현할 것, 난해한
방식은 채택하지 말 것, 작업량은 제약이 아닐 것.

- [x] v1 계획서 결함 진단 7건 **전부 실물 재현** — 코드 읽기가 아니라 실행으로 확인
- [x] v1 처방 중 **3건이 표준 라이브러리 재구현**임을 확인 — 중첩 `async with` /
      `asyncio.gather` / `enqueue_sentinel` 오버라이드로 대체 가능
- [x] v1 이 확인하지 않은 심각도 근거 실측 — uvicorn 0.34.3 은 lifespan task 를 취소하지
      않는다(F-028 등급 조정), `Config.__init__` 이 앱 import 보다 먼저 로깅을 구성한다
      (Wave 6 대안 도출)
- [x] `dictConfig` 네이티브 queue/listener 전환 **실현 가능성 10개 항목 실측** — 추정으로
      계획에 넣지 않기 위해
- [x] v1 에 없던 결함 2건 발견 — F-035(독스트링 자기모순) · F-036(가드 테스트가 없는
      charter 조항을 가리킴)
- [x] v2 계획서 작성 — 9 Wave / 10 Task, 각 Task 에 **「깨지는 기존 테스트」** 명시
- [x] **Wave 0** — REQ-010 선언, ADR-017·ADR-018·ADR-021 확정, ADR-020 미결 등록,
      ADR-019 건너뜀 사유 기록, F-028 ~ F-036 을 ledger 에 Open 으로 등록
- [x] Wave 0 정합성 — ledger Open Fix 수치와 이 체크판의 수렴 선언을 **함께** 갱신
      (게이트 검사 11 은 `수렴선언 AND 열린칸` 일 때만 실패하므로 이 모순을 잡지 못한다)
- [x] **Wave 1** — `test_manager_cancellation_still_runs_remaining_cleanup` 추가,
      **red 확인**: `calls == ['listener_start', 'drain']` — `dispose`·`listener_stop` 이
      실행되지 않고 `first extra item: 'dispose'` 로 누락이 드러난다. production 코드
      무변경. 나머지 13건은 그대로 통과(13 passed / 1 failed).
      부수 확인: `pytest.raises(asyncio.CancelledError)` 는 **통과** — 취소 재전파는 이미
      지켜지고 있고, 깨진 것은 "정리를 끝까지 시도한다" 쪽이다.

> **Wave 1~7 동안 게이트 검사 1(pytest)은 의도적으로 빨갛다.** 실패 테스트를 먼저 쓰는
> 것이 Wave 1 의 인수 조건이기 때문이다. Wave 2 에서 green 으로 바뀐다. 이 기간의 빨간
> 게이트를 고장으로 읽지 말 것.

- [x] **Wave 2** — 종료 조립을 중첩 `async with` 로 전환 (ADR-017 / F-028 · F-035).
      **기존 13건을 한 줄도 고치지 않고 통과** — 계약 보존의 증거다. 새 회귀 테스트가
      red→green (14 passed).
      실물 재현으로 대조: 버그를 드러냈던 그 스크립트가
      `['listener_start','prepare','drain']` → `[..., 'dispose', 'stop_listener']`,
      `state_is_none` False → **True**, 취소는 그대로 재전파.
      전체 **392 passed · skipped 0**(MySQL 8.4 기동 후 실측) · 게이트 **11종 전건 통과**.
      F-035: 모듈 독스트링 7행의 `역순 등록으로 강제한다` 를 제거하고 중첩 구조 설명으로
      교체 — 13행과의 자기모순 해소.
- [x] **Wave 3** — logging listener 소유권을 프로세스로 (ADR-018 / F-029 · F-031).
      red 3건 먼저 확인 후 구현. **실물 대조가 핵심 증거**: DB 가 꺼진 상태에서
      `python main.py` 출력이 **14줄·오류 0건 → 198줄**로 바뀌고
      `Application startup failed` · SQLAlchemy traceback 45줄이 `[app=uvicorn]` 라벨로
      나온다. 순서도 맞다 — uvicorn 최종 로그 **뒤에** `[log-lifecycle] stop` 이 온다.
      전체 **395 passed · skipped 0** · 게이트 **11종 전건 통과**.
- [x] Wave 3 부산물 — **F-037 신규 발견**: `atexit` + `QueueListener.stop()` 의 무한 join.
      계획서 §4.4 가 "daemon 이라 종료를 막지 않는다" 를 근거로 범위 밖에 뒀는데, 그 근거가
      **틀렸다**(atexit 은 daemon 정리보다 먼저 돈다). 작업 중 실제로 2분 멈춤을 관측했고
      계획서 §4.4 를 정정했다. Wave 5 에서 닫는다.
- [x] Wave 3 사전 예측 실패 1건 — "깨지는 기존 테스트" 4건을 적었으나 실제로는 **5건**이었다
      (`test_slow_cleanup_is_bounded_by_timeout` 누락). 사전 목록은 grep 이 아니라 추정으로
      만들었기 때문이다. 다음 Wave 부터는 기대값 문자열을 실제로 검색해 목록을 만든다.
- [x] **Wave 4** — engine `gather` · background task 예외 회수 (F-032 · F-033).
      red 5건 먼저 확인. 실패 내용이 결함을 그대로 드러냈다 — `dispose_engine()` 에서
      `RuntimeError: writer dispose 실패` 가 **밖으로 전파**됐고, 실패 태스크 기록은
      `[]` 인데 asyncio 가 `future: <Task finished ... exception=RuntimeError(...)>` 를
      직접 찍고 있었다.
      신규 `tests/core/test_db_engine_disposal.py` 6건 + background 3건 = **404 passed**,
      게이트 **11종 전건 통과**.
      계약 보존: `dispose_engine()` 시그니처를 바꾸지 않았고(Celery 호출부 무변경),
      그것을 지키는 가드 테스트를 함께 넣었다.
      Wave 3 교훈 적용: 깨질 기존 테스트 목록을 **grep 으로** 확인했고 실제로 0건이었다
      (기존 테스트는 전부 `dispose_engine` 을 monkeypatch 하고 있었다).
- [x] **Wave 5** — `dictConfig` 네이티브 전환 + `TimeoutSentinelListener` (F-030 · **F-037**).
      red 5건 먼저 확인. 세 가지를 함께 처리했다 — ①`enqueue_sentinel()` 오버라이드
      (표준 라이브러리가 독스트링에서 지정한 확장 지점) ②`stop()` 의 join 에 예산
      (F-037, Wave 3 에서 실측한 무한 대기를 닫는다) ③queue/listener 구성을
      `class`/`queue`/`listener`/`handlers` 선언으로 이관(ADR-021).
      `setup.py` 에서 손수 하던 `_listener_targets` 조회와 listener 생성이 사라졌고,
      죽은 팩토리 `build_queue_handler()` 도 제거했다.
      실물 확인: `handler.listener` 가 `TimeoutSentinelListener` 이고 handler 와 queue 를
      공유하며 `atexit` 경로가 정상 종료(exit 0)한다.
      **409 passed · skipped 0** · 게이트 **11종 전건 통과**.
- [x] Wave 5 — Wave 3 교훈 적용 결과: 깨질 기존 테스트를 grep 으로 미리 확정했고
      (`test_root_uses_queue_handler_only` 의 `queue_handler["()"]` 단 1건),
      **예측이 정확히 맞았다.** 추정으로 만들었던 Wave 3 때와 대조된다.
- [x] Wave 5 — `restart_log_listener()`(Celery prefork 경로)에 테스트가 **하나도 없었다.**
      dictConfig 가 만든 listener 를 재사용하게 되면서 fork 후 죽은 스레드 참조를 지워야
      하는데, 검증 없이는 조용히 깨질 자리였다. 회귀 테스트를 함께 추가했다.
- [ ] Wave 6 — uvicorn 로거 연결 대안 확정 후 구현 (ADR-020 · F-036)
- [ ] Wave 7 — 실제 uvicorn subprocess 통합 테스트 2건
- [ ] Wave 8 — 문서·원장 수렴 + `--mysql-required` (F-034)

---

## 종결 상태

> **2026-08-27 — 이 그룹은 다시 열렸다.** Round 11 의 수렴 선언은 F-028(취소 시 정리 중단)과
> F-034(검증 문서가 검사하지 않은 것을 보장한 것처럼 기술)로 **반증됐다.** 아래 "종결" 서술은
> Round 11 시점의 기록이며, 현재 상태가 아니다.

- **Round 12 진행 중** — Wave 0 완료(문서 등록만), Wave 1~8 미착수.
- **ledger Open Fix 9건** (F-028 ~ F-036). F-001 ~ F-027 은 종결(F-023 만 Accept-out-of-scope).
- 마지막 게이트 전건 통과: **검사 11종** · **391 tests** · MySQL 통합 **8건** 실제 실행 —
  Round 11 (2026-08-25). **이 초록은 F-028 ~ F-036 을 하나도 잡지 못했다** — 결함이
  기존 테스트가 보지 않는 축(취소 · 프로세스 종료 · 실제 서버 기동)에 있었기 때문이다.
- **charter §3 인수기준 12칸은 그대로 닫힘.** Round 12 의 인수 기준은 그 12칸이 아니라
  v2 계획서 §11 Definition of Done 이며, 그것을 다 채운 뒤에만 수렴을 다시 선언한다.

**"완료"의 범위는 여기까지다.** 이 체크판이 닫혔다는 것은 *계약으로 정한 검사들이 전부
그린*이라는 뜻이지, 결함이 없다는 뜻이 아니다. 검사하지 않은 범위(부하·성능, 복제 실환경,
Celery 워커 실행, Scalar UI 실렌더링)는 `residual-risk.md` 하단에 적혀 있다.

향후 이 그룹에 새 요청이 오면 Round 13 을 이 아래에 추가한다. `residual-risk.md` 의
R-001~R-006 을 새 finding 으로 올리지 않는다 — 그것은 결함이 아니라 **계약 변경 제안**이다.
