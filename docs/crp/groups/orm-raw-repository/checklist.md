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

---

## 종결 상태

- **미닫힘 항목 0개** — 모든 라운드가 GATE 5 Done.
- **ledger Open Fix 0건** (F-001 ~ F-025 — F-023 만 Accept-out-of-scope, 나머지 전부 Fixed).
- 마지막 게이트 실행: 전건 통과(**검사 11종**) · **391 tests** · MySQL 통합 **8건** 실제 실행 — Round 10 (2026-08-20).
- **charter §3 인수기준 12칸 전부 닫힘** — 칸마다 근거를 명시했고, 게이트 검사 11 이 매번 확인한다.

**"완료"의 범위는 여기까지다.** 이 체크판이 닫혔다는 것은 *계약으로 정한 검사들이 전부
그린*이라는 뜻이지, 결함이 없다는 뜻이 아니다. 검사하지 않은 범위(부하·성능, 복제 실환경,
Celery 워커 실행, Scalar UI 실렌더링)는 `residual-risk.md` 하단에 적혀 있다.

향후 이 그룹에 새 요청이 오면 Round 11 을 이 아래에 추가한다. `residual-risk.md` 의
R-001~R-006 을 새 finding 으로 올리지 않는다 — 그것은 결함이 아니라 **계약 변경 제안**이다.
