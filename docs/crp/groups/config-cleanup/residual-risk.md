# Residual Risk — config-cleanup (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용"으로 박제된 항목은 의도적으로 고치지 않기로 한 것이다. 고쳐야 하면 새 결함이 아니라
> **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | 읽는 코드가 없는 필드 4개가 남아 있다 — `API_VERSION`, `LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT` | LOW | 사용자 결정은 SMTP·업로드·`SESSION_EXPIRE_SECONDS` 세 묶음만이다. 사유와 함께 `UNUSED_ALLOWED` 에 있다(ADR-003) | 2026-10-19 | 존치·삭제를 결정하면 — 지우면 목록에서도 뺀다(낡은 예외는 테스트가 잡는다). **해소 2026-10-19 (Round 2, `8dde820`)** — `API_VERSION` 삭제(F-005), 로그 3필드 연결(F-006·F-007), 예외 목록 삭제(ADR-007) |
| R-002 | 운영 `.env` 에 남은 옛 `SMTP_PASSWORD` 등의 실제 값은 무시되지만 파일에는 남는다 | LOW | ADR-002 — 효과 없는 값이라 기동 거부로 만들지 않았다. README 업그레이드 노트가 "지워도 된다" 를 알린다 | 2026-10-19 | 옛 비밀 값의 파일 보관이 감사 지적을 받으면 |
| R-004 | 콘솔을 끄면(`LOG_CONSOLE_ENABLED=false`) 앱 로그는 출력처가 없어 버려진다 — 앱에는 파일 핸들러가 없다 | LOW | 사용자가 명시적으로 끈 것이고, 기동 때 stderr 경고 한 줄로 알린다(ADR-006 ⑤). 파일 출력을 다시 넣는 것은 NFR-009(파일 핸들러 제거) 결정을 뒤집는 일이다 | 2026-10-19 | 콘솔 없이 앱 로그를 남겨야 하는 배포가 생기면 |
| R-005 | uvicorn CLI·Celery 콘솔 핸들러는 `LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT` 을 **직접 지정했을 때만** 프로젝트 포맷을 쓴다 — 기본값과 같은 값을 적어도 지정으로 본다 | LOW | INV-4(기본 출력 불변)를 지키려는 의도된 구분(ADR-006 ④) | 2026-10-19 | 기본에서도 uvicorn CLI·Celery 를 프로젝트 포맷으로 통일하기로 하면 — 조건만 지운다 |
| R-003 | 사용처 계약은 **이름** 기준이다 — 설정이 아닌 다른 객체의 같은 이름 속성을 읽어도 "읽힘" 으로 센다. 읽힌 값이 실제 동작에 쓰이는지도 보지 않는다 | LOW | ADR-003. 설정 필드는 대문자 상수형 이름이라 충돌이 사실상 없고, 동작까지 보려면 필드별 행위 테스트가 필요하다 | 2026-10-19 | 오탐(지운 필드인데 통과)이 실제로 나오면 — 수신 객체를 `*_settings` 로 좁힌다 |

> R-004 상태(2026-10-19): **해소** — logging-overhaul L5. `LOG_FILE_ENABLED=true` 면 프로세스별 파일(웹 `app.log`·`error.log`, Celery `celery.log`·`celery-error.log`)에 남는다. 콘솔도 파일도 꺼졌을 때만 경고 한 줄(`test_console_disabled_with_files_on_does_not_warn`).

> R-005 상태(2026-10-19): **해소** — logging-overhaul L1(사용자 결정 "포맷 C"). 지정 여부 조건을 지우고 uvicorn CLI·Celery 콘솔 핸들러를 공유 queue 로 바꿔 모든 경로가 항상 프로젝트 형식을 쓴다(`test_every_path_uses_the_project_format`). INV-4(기본 출력 불변)는 이 결정으로 폐기됐다.
