# Residual Risk — logging-overhaul (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용"으로 박제된 항목은 의도적으로 고치지 않기로 한 것이다. 고쳐야 하면 새 결함이 아니라
> **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | 여러 프로세스(uvicorn `--workers` 2 이상·Celery prefork `--concurrency` 2 이상)가 같은 `LOG_DIR` 에 파일을 쓰면 회전이 엇갈린다 — 덮어쓰지는 않지만 한 날짜의 줄이 여러 번호 파일로 흩어진다. 앱은 경고하지 않는다 | MED | ADR-003 — 워커 수를 앱 안에서 확실히 알 수 없다. README "여러 워커 주의" 가 "파일 끔 + 콘솔 + 수집기" 를 지시한다(charter §2-1) | 2026-10-19 | 여러 워커에서 파일 로그가 필요해지면 — 프로세스별 파일 이름(pid)이나 `QueueHandler` → 단일 수집 프로세스 |
| R-002 | `MYSQL_USER` 기본값 `root`(4글자)는 설정하지 않아도 원문 치환 대상이라 경로(`/root/...`)·문장의 `root` 도 `***` 로 바뀐다 | LOW | ADR-006 — 명세 "4글자 미만만 형태 제한". 실제 배포는 전용 계정을 쓴다 | 2026-10-19 | 오탐이 진단을 방해하면 — 기본값과 같은 값은 빼는 규칙을 더한다 |
| R-003 | Celery worker 의 root 레벨은 `celery -l` 이 정한다 — `.env` 의 `LOG_LEVEL` 이 그보다 낮아도 worker 에서는 보이지 않는다(기본 `-l` 은 WARNING) | LOW | ADR-004 — 명령줄 지정을 덮지 않는다. README 에 적었다 | 2026-10-19 | worker 레벨도 `.env` 가 정해야 하면 — 수신자에서 root 레벨을 `lowest_level()` 로 |
| R-004 | uvicorn 접속 줄의 상태 문구가 빠진다(`200 OK` → `200`) — `{message}` 는 레코드의 요청 줄이다 | LOW | ADR-001 — 명세의 요청 줄 형식(`client - "GET /p HTTP/1.1" 200`)과 같고 `python main.py` 경로는 원래 그랬다 | 2026-10-19 | 문구가 필요하면 — `TzFormatter` 에서 접속 레코드만 `http.HTTPStatus` 문구를 붙인다 |
| R-005 | 파일은 진입점(`main.py`·Celery worker)이 있는 프로세스만 쓴다 — `alembic`·`scripts/*`·`celery beat` 는 콘솔만 | LOW | ADR-002 — 명세의 파일은 웹·워커 두 종류다 | 2026-10-19 | beat·스크립트 로그를 파일로 남겨야 하면 — 그 진입점에서 `attach_log_files` 를 부르고 `LOG_FILES` 에 종류를 더한다 |
| R-006 | `fastapi dev`(fastapi-cli)는 이 환경에 설치돼 있지 않아 실기동하지 않았다 — 같은 채택 함수가 핸들러 종류와 무관하게 콘솔 핸들러를 바꾼다는 것만 근거다 | LOW | 의존성 추가는 범위 밖 | 2026-10-19 | `fastapi[standard]` 를 들이면 스모크에 추가 |
