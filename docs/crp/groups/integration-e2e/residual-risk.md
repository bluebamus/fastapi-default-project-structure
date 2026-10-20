# Residual Risk — integration-e2e (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용"으로 박제된 항목은 의도적으로 고치지 않기로 한 것이다. 고쳐야 하면 새 결함이 아니라
> **계약 변경 제안** — charter 를 먼저 바꾼다. "결정 필요" 는 감독자·사용자 결정 전까지 열린 항목이다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | 메서드 분할 경로(컬렉션 `GET`+`POST`, 단건 `GET`+`PATCH`+`DELETE`)의 405 `Allow` 에 마지막으로 맞은 라우트의 메서드만 실린다(예: `/api/v1/blog/posts` 에 `PUT` → `Allow: POST`) | LOW | 사용자 결정 "현행 유지 — 값만 기록"(계획서 §3 L2, ADR-008). 값은 `inventory.md` 의 기록 절 | 2026-10-20 | `Allow` 정확성이 필요해지면 — 경로 단위 405 처리(예외 핸들러에서 같은 경로의 메서드를 모아 싣기) |
| R-002 | 로컬(Windows)의 Celery worker 는 `--pool=solo`, CI(Linux)는 `prefork --concurrency=1` 로 돈다 — 태스크 코드는 같지만 `worker_process_init`·`worker_process_shutdown` 수신자는 prefork 에서만 돈다 | LOW | Windows 에는 fork 가 없다. CI job `e2e` 가 운영 기본값(prefork)으로 같은 시나리오를 돈다 | 2026-10-20 | Windows 에서 prefork 동작 증거가 필요해지면 — WSL 안에서 스위트를 돈다 |
| R-003 | E2E 의 Redis·MySQL 은 영속화하지 않는다(tmpfs·`--save ""`) — 장애 주입 뒤 "재기동 후 세션이 남아 있으면 그대로 쓴다"(README) 는 확인하지 못한다. primary 정지는 스택 재구성으로 끝난다 | LOW | 명세 "down -v 금지 + down 만으로 정리" 는 tmpfs 만 만족한다(익명 볼륨은 `down` 이 지우지 않는다) | 2026-10-20 | 영속 재기동 증거가 필요해지면 — 이름 있는 볼륨 + 정리 단계에 그 볼륨만 지우는 명시 명령(사용자 승인 필요) |
| R-004 | `/ready` 는 writer DB 와 Redis 만 본다 — replica 가 멈춰도 200 이고, 그동안 replica 로 가는 조회(Public GET 등)는 500 `DATABASE_ERROR` 다(primary 대체 없음, L5 실측) | MED | service-hardening ADR-011 이 `/ready` 대상을 DB(writer)·Redis 로 정했다. replica 장애 시 primary 대체는 코드에 없는 정책이다 — 바꾸면 정책 변경 | 2026-10-20 (결정 필요) → **해소 2026-10-20**: 사용자가 (a) 를 골랐다 — 읽기 전용 세션의 replica 연결 오류는 primary 로 한 번 재시도 + WARNING(ADR-010, `a8be33a`). `/ready` 는 그대로 writer·Redis 만 본다(replica 정지 중 200 은 의도) | 읽기 가용성이 필요하면 — (a) replica 실패 시 writer 로 재시도, (b) `/ready` 에 replica 포함, (c) 현행 유지 중 선택 |
