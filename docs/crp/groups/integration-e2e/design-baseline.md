# Design Baseline — integration-e2e (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태(Active/Superseded)만 바꾼다.
>
> **ID 범위:** `REQ-0xx`·`ADR-0xx`·`C-x`·`F-0xx`·`R-0xx` 는 **이 그룹 안에서만** 번호를 매긴다. 그룹 밖에서 인용할 때는
> `integration-e2e ADR-0xx` 처럼 그룹 이름을 붙인다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 갈림길(산출물·복제·CI·장애 주입·포트·keepalive·Playwright)은 사용자가 계획서 §0·§5 로 확정했다(2026-10-19). 나머지는 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-20 · 변경 이력: (없음)

## 1. 목적 / 배경

사용자 지시 "통합 테스트 진행해줘"(2026-10-20). 계획서(작업 폴더 `integration-test-plan.md`, 사용자 확정)의 W1~W9·L1~L6 을
이 저장소에서 수행한다 — 실제 MySQL 복제·Redis·uvicorn·Celery·브라우저 위에서 API·관리 화면·백그라운드·장애·운영 도구를
전수로 돌리고, 실제 앱에서 뽑은 인벤토리의 모든 칸이 실행됐는지 대조한다. 그 전에 W0: 기존 통합 테스트가 접속 대상을
명시하지 않아 남의 로컬 Redis 에 붙은 사고의 구조를 없앤다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-20 | W0 "테스트가 남의 Redis 에 붙는 구조 제거" | Redis 가 필요한 fixture 는 `REDIS_HOST`·`REDIS_PORT` 가 명시되지 않으면 `pytest.fail`(이유·방법). 명시됐는데 닿지 않으면 기존 skip. 자식 서버 env 에 확인한 대상(+부모가 준 `REDIS_PASSWORD`, 없으면 빈 값)을 넘겨 `.env` 가 바꾸지 못하게. CI 에 변수 명시 | Active | ADR-005, F-001 |
| REQ-002 | 2026-10-19 | 계획서 §0 D1~D4·포트·keepalive·Playwright | 영구 스위트 `tests/e2e/`(마커 `e2e`), GTID replica 위 검증, 매 push CI job `e2e`(skip·xfail 금지), 장애 주입 포함. 포트 MySQL 13321·13322, Redis 16391, 앱 18091(127.0.0.1). 실행 직전 점유 검사, 접속 대상 검사 | Active | ADR-001~004 |
| REQ-003 | 2026-10-19 | 계획서 §3 공통 통과 기준 | 실패 0 · skip 0 · xfail 0 · 인벤토리 빈 칸 0 · 실행 로그 비밀값 grep 0 | Active | ADR-006, ADR-007 |
| REQ-004 | 2026-10-19 | 계획서 §3 L2~L6 | L2 operation × 7칸, L3 시나리오 8종, L4 관리 화면 6항목, L5 장애 5종, L6 운영 4항목 | Active | ADR-006 |
| REQ-005 | 2026-10-20 | 명세 "로깅 쪽 새 검사 대상" | 실행 경로별 같은 형식·헤더, 앱별 레벨, 프로세스별 파일·회전·보관, DSN·설정 비밀값 원문 0건 | Active | F-003 |
| REQ-006 | 2026-10-19 | 계획서 §5-1 | 통합 테스트가 찾은 결함은 테스트를 먼저 고정하고 별도 커밋으로 고친다. 정책을 바꾸는 수정은 멈추고 보고 | Active | F-001~F-005 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-20 | 스택은 **별도 파일** `compose.e2e.yaml`(프로젝트 `itest-default`)이다. `compose.test.yaml` 은 그대로 둔다 | 기존 파일은 고정 `container_name`·고정 계정·포트를 쓰고 `gate`·`mysql` job 이 그대로 의존한다. E2E 는 실행마다 무작위 비밀번호, 복제 2대, 컨테이너 정지·재기동을 하므로 섞으면 서로를 깨뜨린다 | Active | — |
| ADR-002 | 2026-10-20 | **하네스가 스택을 소유한다**(`tests/e2e/stack.py`): 점유 검사 → 비밀값 생성 → `up --wait` → 127.0.0.1 도달 확인 → GTID 복제 부착(`RESET BINARY LOGS AND GTIDS` 후 `SOURCE_AUTO_POSITION=1`) → Alembic → `create_superuser` → uvicorn·Celery worker → 끝나면 프로세스 정지 + `down`(tmpfs 라 `-v` 불필요). Docker 가 PATH 에 없고 Windows 면 `wsl -e` + 실행 중 keepalive | 장애 주입(L5)이 컨테이너를 멈췄다 켜야 하고, 실행마다 무작위 비밀값을 compose 와 앱이 함께 알아야 한다. CI 와 로컬이 같은 코드 경로를 쓴다. 데이터는 tmpfs — 명세 "down -v 금지" 와 정리 요구를 함께 만족 | Active | — |
| ADR-003 | 2026-10-20 | 자식 프로세스는 **빈 작업 디렉터리**에서 OS 필수 변수만 물려받아 띄우고, 설정은 전부 환경 변수로 준다(`ENV=development`, `DEBUG=false`). 시작 전에 모든 DSN·Redis 대상이 127.0.0.1 + 표의 포트인지 검사한다(`check_targets`) | `.env` 는 작업 디렉터리 기준으로 읽힌다 — 저장소에서 띄우면 개발자 `.env` 가 접속 대상을 바꾼다(W0 와 같은 사고). `ENV=development` 라 배포 설정 검사(예시 값·짧은 키)가 실제로 돈다. `TRUSTED_PROXY_HOPS=1` + 클라이언트마다 다른 `X-Forwarded-For` 로 레이트 리밋 카운터를 테스트끼리 나눈다 | Active | — |
| ADR-004 | 2026-10-20 | `tests/e2e/` 는 마커식에 `e2e` 가 없으면 **deselect**(skip 아님). 마커 `e2e` 등록, CI job `e2e` 만 `-m e2e` 로 돈다. Playwright(Chromium)를 dev 의존성으로 추가 | 기본 실행·`-m "not mysql"`·`review_gate` 는 Docker 없이 돌아야 한다. deselect 는 "안 돌았다" 가 요약에 드러나고 skip 판정과 섞이지 않는다. Playwright 는 계획서 §0 에서 허용(관리 화면의 JS CSRF 주입은 실제 브라우저로만 검증된다 — default R-005) | Active | — |
| ADR-005 | 2026-10-20 | W0: `require_redis` 가 `(host, port)` 를 돌려주고 `ServerProcess(argv, port, redis_target)` 가 그 값을 자식 env 로 넘긴다. 미지정이면 `pytest.fail` | fixture 가 확인한 대상과 자식이 붙는 대상이 같아야 한다. 기본값을 남기면 다시 남의 Redis 에 붙는다 | Active | — |
| ADR-006 | 2026-10-20 | **인벤토리 대조**: 테스트가 `cover(kind, item, cell, na=None)` 로 장부에 적고, 마지막 파일 `test_zz_inventory.py` 가 실제 앱에서 operation(`AccessPolicyGuard().routes`)·관리 뷰(`ADMIN_VIEWS`)·Celery 태스크·beat 일정·Redis 접두어(소스 스캔)를 뽑아 칸 목록을 만들고, 빈 칸·모르는 칸이 있으면 실패. 행위 목록(관리 화면 요청 종류·장애·운영·로깅)은 계획서에서 옮긴 고정 표. 결과는 `inventory.md` | 새 API·뷰·태스크·키가 생기면 테스트가 없어도 초록인 상태를 막는다. N/A 는 사유 문자열로 적어 "빈 칸 금지" 를 지킨다 | Active | — |
| ADR-007 | 2026-10-20 | **비밀값 grep** 은 마지막 테스트(`test_zz_secrets.py`)에서 앱·worker 를 멈춰 큐를 비운 뒤, 실행 디렉터리의 모든 `*.log*`(앱·worker·beat·도구 출력, 프로세스 파일·회전 파일)에서 실행마다 만든 비밀값과 발급 토큰 원문을 찾는다 | 정지 전에는 큐에 남은 줄을 못 본다. 값은 실패 메시지에도 싣지 않는다 | Active | — |
| ADR-008 | 2026-10-20 | 메서드 분할 경로의 405 `Allow` 는 **값만 기록**한다(`Allow` 가 있고 그 경로 메서드의 부분집합인지 판정, 실제 값은 `NOTES`) | 사용자 결정(계획서 §3 L2 "현행 유지 — 값만 기록") | Active | — |

## 4. 불가침 제약

- C-1: 접속은 127.0.0.1 의 이 스택(13321·13322·16391·18091)뿐. 외부 DB(115.68.199.140)·`*-testdb`·남의 컨테이너(6379 등)에 붙지 않는다.
- C-2: 이 작업이 만든 compose 프로젝트(`itest-default`)에만 up·stop·start·down·logs·exec. `down -v` 금지.
- C-3: `.env` 를 읽지 않는다(하네스는 빈 작업 디렉터리에서 자식을 띄운다).
- C-4: 정책을 바꾸는 수정(권한·폐기 규칙·응답 형식·설정 의미)은 하지 않고 보고한다.

## 5. 변경 이력

| 날짜 | 변경 |
|---|---|
| 2026-10-20 | 그룹 개설(REQ-001~006, ADR-001~008) |
