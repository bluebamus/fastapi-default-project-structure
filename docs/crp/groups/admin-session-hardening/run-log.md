# Run Log — admin-session-hardening (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. 마지막 라운드가 `CONVERGED` 이고 이후 코드·계약이 안
> 바뀌었으면 동일 요청은 "할 일 없음".

작업 기준선 base SHA: `90cf027` (main, 그룹 개설 직전). 브랜치 `feat/admin-session`. 코드 커밋 `ba0e098`(세션·CSRF)·`2768083`(기간 필터)·`25901ae`(관리 화면 폐기 훅 — 추가 범위).

## 라운드 기록

### Round 1 — 2026-10-19 · 원 명세 (Redis 서버 세션 · 로그인 이후 CSRF · 기간 필터 · 405 사용자 결정) + 감독자 추가 범위(REQ-003)
- **트리거:** REQ-001, REQ-002(사용자 결정), REQ-003(감독자 추가 범위 — 관리 화면 수정·삭제의 폐기 조건)
- **현황(변경 전):**
  - 세션 — `AuthenticationBackend.__init__` 이 starlette `SessionMiddleware`(itsdangerous `TimestampSigner`)를 붙인다. 쿠키 내용 전체(`user_id`·`csrf_token`)가 서명 JSON. `itsdangerous` 의 소비처는 이 미들웨어와 테스트뿐(`grep`) → 제거.
  - 폐기 — refresh `revoke_user` 는 `UserService.update_user`(`is_active=False`)·`delete_user` 두 곳. 관리 화면(sqladmin)의 사용자 수정·삭제는 `UserService` 를 거치지 않는다. 비밀번호 변경 경로는 API·관리 화면 모두 없다.
  - CSRF — sqladmin 0.32 소스·템플릿·`statics/js/main.js` 조사 결과 아래 표. 로그인 이후 요청에는 토큰이 없고 로그아웃은 GET.
  - 템플릿 — `init_templating_engine` 이 `ChoiceLoader([FileSystemLoader(templates_dir), PrefixLoader({"sqladmin_original": ...}), PackageLoader])` 라 덮어쓴 템플릿이 원본을 `sqladmin_original/` 로 확장할 수 있다.
  - 필터 — `ModelView.get_model_objects` 는 연산 필터에 `request.query_params.get(name)` 값 하나와 `{name}_op` 하나만 넘긴다.
  - sqladmin 훅 — `_queries.py` `_update_async`: `on_model_change(data, obj)` → 값 적용 → commit → `after_model_change`. `_delete_async`: `on_model_delete` → delete → commit → `after_model_delete`.
- **결정:** ADR-001~007
- **신규 finding:** MED 4(F-001·F-002·F-003·F-005) · LOW 1(F-004) — 전부 Fixed

#### sqladmin 0.32 의 상태 변경 요청과 보호 방식 (명세 §2)

| 요청 | 메서드·경로 | 보내는 방식(sqladmin) | 보호 |
|---|---|---|---|
| 로그인 | `POST /admin/login` | 덮어쓴 `login.html` 폼 | 폼 hidden `csrf_token` → `AdminCsrfMiddleware`(실패 시 로그인 화면 403) |
| 생성 | `POST /admin/{identity}/create` | `create.html` 네이티브 폼 | 스크립트가 submit 때 hidden `csrf_token` → 미들웨어 |
| 수정(저장·다른 이름으로 저장) | `POST /admin/{identity}/edit/{pk}` | `edit.html` 네이티브 폼 | 같음 |
| 삭제(행·상세 모달) | `DELETE /admin/{identity}/delete?pks=…` | `main.js` `$.ajax`(XHR) | 스크립트의 XHR 패치가 `X-CSRF-Token` → 미들웨어 |
| 일괄 삭제(목록 선택) | 같은 DELETE, `pks=a,b,…` | `main.js` `#action-delete` → 같은 모달 | 같음 |
| CSV import | `POST /admin/{identity}/import` | `main.js` `fetch(FormData)` | 스크립트의 fetch 패치가 헤더 → 미들웨어. 모든 뷰 `can_import=False`(비활성) |
| 사용자 정의 action | `GET /admin/{identity}/action/{slug}` | `main.js` `window.location.href` | 등록된 action 없음 — `test_no_view_registers_a_custom_get_action` 이 막는다(R-002) |
| 로그아웃 | `GET /admin/logout` → **`POST`** | `layout.html` `<a href>` | 라우트를 POST 전용으로 교체(GET 405), 스크립트가 링크 클릭을 토큰 실은 POST 폼으로 → 미들웨어 |
| 내보내기·목록·상세·ajax lookup·파일 내려받기/미리보기·언어 전환 | GET | 링크·select2 | 상태 변경 없음 — 대상 아님 |

#### fail-on-revert (변이 → 실패한 테스트)

변이는 대상 파일을 작업 폴더 밖(`C:\Users\rnd15\.claude\jobs\456c49a4\tmp\default\admin-session\backup`)에 복사해 두고 적용 → 해당 테스트 실행 →
복사본으로 복원했다(`git checkout` 미사용, 복원 뒤 작업 트리 해시 동일 확인). 20건 모두 실패.

| 변이 | 결과 |
|---|---|
| 백엔드·조립을 서명 쿠키(main)로 | 1 failed, 46 errors |
| `UserService` 관리 세션 폐기 호출 제거 | 3 failed |
| `UserService` 강등 조건 제거 | 1 failed |
| `UserAdmin` 폐기 훅 제거(main) — 1차 테스트 기준 | 1 failed |
| 로그인 시 `rotate_session` 제거 | 2 failed |
| 기존 세션 저장의 `SET XX` 제거 | 1 failed |
| 절대 만료 상한 제거(TTL=idle 고정, load 의 절대 만료 확인 제거) | 2 failed |
| Redis 장애를 삼키고 빈 세션으로 통과 | 1 failed |
| `AdminCsrfMiddleware` 제거 | 21 failed |
| 로그아웃 POST 전용 교체 제거 | 4 failed |
| `base.html` 덮어쓰기 삭제 | 2 failed |
| 기간 필터 `admin_filters.py`(main) | 15 failed |
| 기간 필터 템플릿(main) | 1 failed |
| 설정 검증(main `config.py`) | 4 failed |
| (추가 범위) `UserAdmin` 훅을 커밋된 `after_*` 버전으로 | 2 failed(비밀번호·폐기 실패 시 미저장) |
| (추가 범위) 강등 조건 제거 | 2 failed |
| (추가 범위) 비활성화 조건 제거 | 2 failed |
| (추가 범위) 비밀번호 조건 제거 | 1 failed |
| (추가 범위) 변경 비교 없이 항상 폐기 | 2 failed(일반 수정·같은 해시) |
| (추가 범위) 삭제 훅 제거 | 1 failed |

#### 게이트

| 검사 | 결과 |
|---|---|
| `ruff check .` · `ruff format --check .` | 통과 |
| mypy(규칙 파일 방법, `--no-binary-package mypy`) | 204 파일 이슈 없음 |
| `pytest -m "not mysql"` 작업 트리(fakeredis TCP 를 `REDIS_PORT` 로) | 1231 passed, 19 deselected, skip 0 |
| `pytest -m "not mysql"` `.env` 없는 저장소 밖 클론 | 첫 실행 2 failed(문서 경로 검사가 `sqladmin_original/base.html` 을 저장소 파일로 봄 → `ALLOWED_MISSING` 에 이유와 함께 추가) → 재실행 1231 passed, 19 deselected, skip 0 |
| `pytest -m mysql --collect-only` | 19 수집(실행하지 않음 — CI) |
| `review_gate --fast`(ruff·mypy·pip-audit·계층·공개 API·포트·테이블 삭제·인용 커밋·요구 ID·async·프로세스 테스트·charter 정합) | 전부 PASS |
| alembic | 변경 없음(`migrations/` diff 없음) |
| 실기동 스모크(SQLite 파일 DB·fakeredis TCP·uvicorn, 관리 화면만 조립한 런처) | 로그인 302 → 쿠키에 43자 sid 만·속성(Path·SameSite·HttpOnly·Max-Age=28800) → 토큰 없는 생성 403 / 토큰 생성 302 → 과거 기간 필터에서 빠짐·열린 기간에서 보임 → 토큰 없는 삭제 403 / 헤더 토큰 삭제 200 → GET 로그아웃 405·로그인 유지 → POST 로그아웃 302 → 이전 쿠키 사본 302(로그인 화면) |
| 인라인 스크립트(렌더 결과를 node 로) | `node --check` 통과, DOM 스텁 동작 확인(POST 폼 hidden·XHR DELETE 헤더·GET/타 출처 무헤더·fetch POST 헤더·로그아웃 링크 → POST 폼) |

- **수렴:** CONVERGED — Open Fix 0, charter §3 전부 그린.

### Round 2 — 2026-10-19 · 후속 (R-004 해소 — 관리 화면 경로의 API refresh 폐기)
- **트리거:** REQ-004(감독자 후속 지시, Round 1 은 main `d353c86` 으로 병합). 브랜치 `fix/admin-ui-refresh-revoke`(main 에서), 코드 커밋 `15c1f70`.
- **현황(변경 전):** `UserAdmin.on_model_change`·`on_model_delete` 는 관리 세션만 폐기했다. API 경로 `UserService` 는 비활성화·삭제에서 refresh family 를 폐기한다(강등은 폐기하지 않음 — 회전 때 DB 값으로 재발급).
- **결정:** ADR-008. 신규 finding: LOW 1(F-006) — Fixed.

#### fail-on-revert

같은 방식(작업 폴더 밖 백업 → 변이 → 테스트 → 복원, 복원 뒤 파일 해시 동일 확인). 2건 모두 실패.

| 변이 | 결과 |
|---|---|
| `app/features/user/admin.py` 를 main(관리 세션만 폐기)으로 | 5 failed(비활성화·강등·삭제·비밀번호의 refresh 폐기, refresh 저장소 실패 시 미저장) |
| `_revoke_credentials` 에서 refresh 폐기 줄 제거 | 5 failed |

#### 게이트

| 검사 | 결과 |
|---|---|
| `ruff check .` · `ruff format --check .` | 통과 |
| mypy(규칙 파일 방법) | 204 파일 이슈 없음 |
| `pytest -m "not mysql"` 작업 트리(fakeredis TCP 를 `REDIS_PORT` 로, 실제 DB·Redis 접속 없음) | 1232 passed, 19 deselected, skip 0 |
| `pytest -m "not mysql"` `.env` 없는 저장소 밖 클론 | 1232 passed, 19 deselected, skip 0 |
| alembic | 변경 없음 |

- **수렴:** CONVERGED — Open Fix 0, charter §3 전부 그린.
