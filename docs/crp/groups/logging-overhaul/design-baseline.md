# Design Baseline — logging-overhaul (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태(Active/Superseded)만 바꾼다.
>
> **ID 범위:** `REQ-0xx`·`ADR-0xx`·`C-x`·`F-0xx`·`R-0xx` 는 **이 그룹 안에서만** 번호를 매긴다. 그룹 밖에서 인용할 때는
> `logging-overhaul ADR-0xx` 처럼 그룹 이름을 붙인다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길은 사용자 결정(2026-10-19)으로 받았고, 나머지는 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-19 · 변경 이력: (없음)

## 1. 목적 / 배경

로그를 Django `LOGGING` 처럼 `.env` 로 세부 조정하고, 앱·uvicorn·Celery 의 출처를 헤더로 구분하되 형식은 하나로, 모든 줄에
모듈·클래스·함수·시각을 싣고, 파일을 날짜·크기로 회전·보관하며, DB 계정 같은 비밀값이 어디에도 나오지 않게 한다.
변경 전에는 uvicorn CLI·Celery 가 기본값일 때 각자 형식을 썼고(config-cleanup ADR-006 ④), 앱 파일 출력이 없었으며
(NFR-009), 헤더별 레벨이 없었고(ADR-019 의 수용 위험), DSN 사용자명·설정 비밀값 원문은 가려지지 않았다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-19 | "앱별·Celery 별 헤더로 출처를 구분하되 출력 포맷은 하나로" · 사용자 결정 "포맷 C — 모든 실행 경로가 항상 프로젝트 형식" | 앱·`python main.py`·`uvicorn main:app`(·`fastapi dev`)·Celery(메인·태스크)의 콘솔·파일이 같은 `TzFormatter`·포맷을 쓴다. "기본값이면 도구 형식" 분기 제거. 접속 줄은 요청 줄 유지, `--logfile` 존중 | Active | ADR-001, F-003 |
| REQ-002 | 2026-10-19 | 명세 L2 | 헤더 판별은 한 함수. 외부 코드는 로거 이름으로 `celery`(celery·kombu)·`uvicorn`·`sqlalchemy`·`alembic`·`ext` | Active | ADR-005 |
| REQ-003 | 2026-10-19 | "모든 줄에 모듈·클래스·함수·시간" | `LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT` 에 필수 자리표시자 7개가 없으면 기동 거부, 메시지에 빠진 목록 | Active | ADR-008, F-006 |
| REQ-004 | 2026-10-19 | "레벨로 관리, `.env` 로 제어" | `LOG_LEVEL`·`LOG_CONSOLE_LEVEL`·`LOG_FILE_LEVEL` + 헤더별 `LOG_APP_LEVELS`. 잘못된 값은 기동 오류, 모르는 헤더는 경고 | Active | ADR-004, F-004 |
| REQ-005 | 2026-10-19 | "로그 파일을 로테이트·분할, 보관 기간 설정" · 사용자 결정 "날짜+크기, 보관 일수", "프로세스별 + 에러" | `LOG_DIR` 아래 웹 `app.log`·`error.log`, Celery `celery.log`·`celery-error.log`. 자정 날짜 회전 + 하루 안 크기 분할 + `LOG_RETENTION_DAYS` | Active | ADR-002, ADR-003, ADR-007, F-005 |
| REQ-006 | 2026-10-19 | "DB id·비밀번호 같은 주요 정보는 로그에 나오면 안 된다" · 사용자 결정 "DSN id·비밀번호와 `.env` 비밀값 원문" | DSN 의 사용자명·비밀번호를 가리고, 설정 비밀값 원문을 메시지·인자·traceback·stack 어디서든 가린다(4글자 미만은 계정 형태에서만) | Active | ADR-006, F-001, F-002 |
| REQ-007 | 2026-10-19 | 명세 L8 | README 로깅 절(Django `LOGGING` 대응표·키 표·파일·다중 워커·업그레이드 노트), ARCHITECTURE §9·부록, server-lifecycle 안내서, DEVELOPMENT §11, `.env.example` | Active | — |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-19 | 남이 만든 핸들러는 **고쳐 쓰지 않고 바꿔 단다** — `setup.adopt_foreign_handlers(logger)`: 공유 queue 가 아닌 핸들러 중 파일이 아닌 것은 떼고 공유 queue 핸들러를 단다(핸들러가 하나라도 있던 로거만). 파일 핸들러(Celery `--logfile`)는 남겨 `LOG_FILE_FORMAT` 의 `TzFormatter` 와 queue 와 같은 필터(redact·context·app_levels)를 입힌다. 부르는 곳: `configure_logging()`(uvicorn 3종 — CLI 경로), Celery `after_setup_logger`·`after_setup_task_logger`. `TzAccessFormatter` 는 두지 않는다 — 접속 레코드의 `getMessage()` 가 이미 `client - "GET /p HTTP/1.1" 200` 이라 `{message}` 로 충분하다(`python main.py` 경로가 이미 그렇게 출력). 옛 queue 핸들러(재구성 전)도 남의 것으로 본다 | 같은 목적은 한 곳 — 포맷·필터·출력처(콘솔·파일)가 queue 하나에 이미 모여 있다. 핸들러마다 포매터를 바꾸면 파일 출력·헤더별 레벨·`LOG_CONSOLE_ENABLED` 를 경로마다 다시 구현해야 한다. 핸들러가 없던 로거를 건드리지 않아 `--no-access-log` 가 유지된다. `AccessFormatter` 상속은 `{message}` 와 같은 줄을 만드는 두 번째 포매터일 뿐이다(상태 문구 `OK` 만 다르다 — R-004) | Active | config-cleanup ADR-006 ④ |
| ADR-002 | 2026-10-19 | 파일은 **프로세스별**이고 에러 파일도 나눈다: 웹 `app.log`·`error.log`, Celery `celery.log`·`celery-error.log`(`setup.LOG_FILES`). 프로세스 종류는 진입점이 `setup.attach_log_files(kind)` 한 함수로 정한다 — 웹은 `main.py` import 시점, Celery 는 worker 의 `after_setup_logger` 수신자. 파일 핸들러는 dictConfig 가 아니라 **listener** 의 출력처에 더한다(여러 번 불러도 한 번) | 명세 L5 는 `error.log` 공유를 "검토" 로 열어 두었다. 웹과 worker 가 한 파일을 회전시키면 서로 rename 이 엇갈린다 — 나누면 한 파일의 쓰는 이가 한 프로세스 계열뿐이다. import 시점 판단은 불가능하다(웹도 태스크를 보내려고 `app.celery.app` 을 import 할 수 있다). `after_setup_logger` 는 worker 에서만 오고, 웹은 `main.py` 를 import 해야만 뜬다. lifespan 이 아니라 import 시점인 이유는 uvicorn 의 `Waiting for application startup` 이 lifespan 전에 나오기 때문이다. listener 에 붙여 파일 쓰기·회전이 요청 event loop 밖에서 돈다(NFR-009 유지) | Active | — |
| ADR-003 | 2026-10-19 | 회전 핸들러 `DailySizeRotatingFileHandler`(`app/utils/logs/handlers.py`, `TimedRotatingFileHandler` 상속): `computeRollover` 를 **포매터와 같은 시간대**의 다음 자정으로(production·staging UTC, 그 밖 `TIME_ZONE`), 날짜 교체는 `<base>.YYYY-MM-DD`, 하루 안 크기 초과는 `<base>.YYYY-MM-DD.N`. 이미 있는 이름은 덮지 않고 다음 번호. 교체 때 `retention_days` 보다 오래된 날짜(분할 포함)를 지운다 — `date < today - N` 만, 0 이면 지우지 않음. 빈 파일은 나누지 않는다. `LOG_BACKUP_COUNT` 는 되살리지 않고 `LOG_RETENTION_DAYS` 로 대체. 다중 프로세스는 감지하지 않고 문서로만 알린다 | 파일 이름의 날짜가 줄의 시각과 같은 날이어야 찾을 수 있다 — UTC 로 찍는 운영에서 로컬 자정에 자르면 하루가 두 파일에 걸친다. 개수 보관은 크기 분할과 섞이면 뜻이 없다(하루 50개면 개수 5 는 몇 시간). 표준 `TimedRotatingFileHandler` 는 같은 이름을 지우고 덮어 여러 프로세스에서 유실이 된다. `--workers`·`WEB_CONCURRENCY`·gunicorn·Celery prefork 를 앱 안에서 확실히 알 방법이 없어 경고는 오탐·누락이 생긴다 — 명세가 허용한 "문서만" | Active | — |
| ADR-004 | 2026-10-19 | 헤더별 레벨은 **필터 하나** `AppLevelFilter(levels, default)` — queue 의 `ContextFilter` 바로 뒤(`["sql_noise","redact","context","app_levels"]`), 남의 파일 핸들러에도 같은 필터. `LOG_APP_LEVELS="blog=DEBUG,celery=INFO"` 는 `config.parse_app_levels()` 가 검증(형식·표준 레벨 이름, 대소문자 무시). root·queue·uvicorn 로거 레벨은 `lowest_level()`(LOG_LEVEL 과 헤더별 값의 최솟값). 지정 없는 헤더는 `LOG_LEVEL`. 모르는 헤더는 `configure_logging()` 이 WARNING 한 줄(`filters.known_app_names()` — 기능 폴더 + 고정 헤더) | ADR-019(로거를 등록하지 않는다)를 지킨다 — `loggers` 키를 쓰면 "손댈 곳 0" 이 깨진다. 키를 헤더로 두면 헤더 규칙(ADR-005)과 레벨이 같은 이름을 쓴다. 새 기능이 아직 없을 수 있어 모르는 키는 거부하지 않는다. Celery worker 의 root 레벨은 `celery -l` 이 정하므로 그대로 둔다(R-003) | Active | — |
| ADR-005 | 2026-10-19 | 헤더 판별은 `filters._app_from_path(pathname, logger_name="")` 하나. 저장소 안 코드는 종전 경로 규칙, 저장소 밖(`site-packages`·stdlib·`<string>`)은 로거 이름 첫 조각을 표 `_EXTERNAL_LOGGER_APPS` 로, 없으면 `ext`. `TzFormatter` 는 `appname` 이 비면 같은 함수로 채운다. `StaticAppFilter` 와 `setup_uvicorn_logging()` 의 `uvicorn_app` 필터는 지운다 | 판별을 한 표에 모은다(명세). 로거 이름 판별로 uvicorn 라벨이 저절로 붙어 별도 필터가 남는 일만 한다. ContextFilter 를 거치지 않는 경로(남의 핸들러)도 같은 헤더를 갖는다 | Active | — |
| ADR-006 | 2026-10-19 | ① DSN 사용자명 패턴을 `_SECRET_PATTERNS` 정본에 더한다 — `scheme://user:pass@` → `scheme://***:***@`, `scheme://user@` → `scheme://***@`. ② 설정 비밀값 목록 `config.LOG_SECRET_SETTINGS`(MYSQL_USER·MYSQL_PASSWORD·MYSQL_REPLICA_USER·MYSQL_REPLICA_PASSWORD·REDIS_PASSWORD·ACCESS/REFRESH_TOKEN_SECRET_KEY·SESSION_SECRET_KEY)와 `config.log_secret_values()`(빈 값 제외, 긴 값 먼저). `filters.SECRET_VALUES` 가 import 때 받아 `redact()` 가 먼저 원문 치환. 4글자 미만은 `user=`·`username=`(따옴표·`:` 포함) 뒤에서만. ③ 계약 테스트: 모든 Settings 필드 중 이름이 `_USER`·`_PASSWORD`·`_KEY` 로 끝나거나 `SECRET` 을 담으면 목록에 있어야 한다 | 패턴 정본 한 곳(log-redaction ADR-001)을 고쳐 메시지·인자·traceback·stack·DEBUG 500 detail 이 함께 덮인다. 짧은 계정명(`app`·`db`)을 원문으로 가리면 일반 단어·경로가 망가진다. 목록을 config 에 두어 새 설정과 같은 파일에서 고친다 | Active | — |
| ADR-007 | 2026-10-19 | 새 키 기본값: `LOG_FILE_ENABLED=false`, `LOG_DIR=logs`, `LOG_FILE_LEVEL` 없음(= `LOG_LEVEL` 규칙), `LOG_FILE_FORMAT` = 콘솔 기본 포맷, `LOG_MAX_SIZE_MB=10`(1 이상), `LOG_RETENTION_DAYS=30`(0 이상) | 이 저장소의 **현재** 관례는 NFR-009 이후 콘솔 + 수집기다 — 켜 두면 테스트·스크립트·여러 워커 배포가 파일을 만든다. NFR-009 이전 이 저장소의 파일 설정은 `LOG_FILE_ENABLED=true`·`LOG_MAX_SIZE_MB=10` 이었다(`f88dc5f^`) — 크기는 그 값을 따른다. 보관 일수는 명세 기본 30 | Active | — |
| ADR-008 | 2026-10-19 | 포맷 validator(`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT` 공용)는 샘플 렌더 뒤 `string.Formatter().parse` 로 쓰인 필드를 모아 `config.LOG_REQUIRED_FIELDS`(asctime·levelname·appname·module·classname·funcName·message) 중 빠진 것을 `ValueError` 로 알린다 | 렌더 검사(config-cleanup ADR-006 ⑥)는 모르는 필드만 막고 빠진 필드는 막지 못한다. 기본 포맷은 이미 7개를 모두 담는다(`test_default_formats_have_every_required_field`) | Active | — |

## 4. 불가침 제약

- **C-1**: 앱 dictConfig 에 `loggers` 키를 두지 않는다(ADR-019 — 헤더별 레벨은 필터).
- **C-2**: 파일 쓰기·회전은 listener 스레드에서만 일어난다(NFR-009). dictConfig·root 에 파일 핸들러를 직접 두지 않는다(`test_no_file_handlers_in_any_environment`).
- **C-3**: 마스킹 패턴의 정본은 `filters._SECRET_PATTERNS`, 비밀 설정 목록의 정본은 `config.LOG_SECRET_SETTINGS` 하나다.
- **C-4**: 선행 그룹의 Active 불가침 제약을 계승한다. config-cleanup INV-4(기본 출력 불변)는 REQ-001 사용자 결정으로 폐기됐다.

## 5. 변경 이력

- v0.1 (2026-10-19): 최초 작성. REQ-001~007, ADR-001~008, C-1~C-4.
