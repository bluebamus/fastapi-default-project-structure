# Charter — access-policy  (Charter v0.1 / 2026-10-13)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 라운드 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 1 | `app/core/security/access.py`(신규) | 소스 | 접근 수준 4개, `AccessPolicyGuard`, `AccessPolicyError` |
| 1 | `main.py` | 소스 | health·ready·`/docs` 에 `Public`, 조립 끝 `verify(app)` |
| 1 | `app/features/{auth,blog,catalog,home,reply,reports,sns,user}/api/routers/v1/*.py` | 소스 | 뷰 단위 선언, home·reports 라우터 단위 의존성 제거 |
| 1 | `app/core/security/__init__.py`·`dependencies.py` | 소스(docstring) | 사용 예 갱신 |
| 1 | `scripts/review_gate.py` | 스크립트 | 요구 ID 출처에 이 그룹 추가 |
| 1 | `tests/core/test_access_policy.py`(신규), `tests/test_authorization.py`, `tests/test_main.py` | 테스트 | |
| 1 | `README.md`, `docs/guides/ARCHITECTURE.md`·`DEVELOPMENT.md`·`admin-auth-guide.html`·`feature-development-guide.html` | 문서 | |

## 2. 계약 (Contract)

### 2-1. 지원 구성

- `log-redaction-fixes` charter §2-1 과 같다. FastAPI 0.141(`iter_route_contexts`)을 전제로 한다.

### 2-2. 위협 모델

- 방어한다: 인증 선언을 빠뜨린 새 뷰가 공개로 배포되는 것, 인증 없는 쓰기가 의도 표시 없이 열리는 것(`Public` 을 쓰기에),
  모순된 선언, 라우터 중첩·문서 숨김(`include_in_schema=False`) 뒤에 숨은 미선언 뷰.
- 방어하지 않는다: **잘못 고른** 수준(선언은 있지만 의도와 다름 — 예시는 `EXPECTED_ACCESS` 가 고정하나 새 뷰는 사람이 판단, R-001),
  `Mount`·WebSocket 라우트(R-002), 소유권 판정(서비스 `OwnershipPolicy` — 기존 테스트가 고정).

### 2-3. 불변식

- **INV-1**: 앱이 서빙하는 모든 `APIRoute` 는 접근 수준을 정확히 하나 선언한다. 아니면 `main` import 가 실패한다.
- **INV-2**: 응답 코드와 OpenAPI(security 포함)는 변경 전과 같다.
- **INV-3**: 라우트별 기대 수준 표는 `EXPECTED_ACCESS` 하나이고, 판정은 `AccessPolicyGuard.levels()` 하나다.

## 3. 인수 기준 — 전부 그린

- [x] **가드 단위** — 선언 없음·이중 선언·쓰기+Public·안전+PublicWrite 위반, 인자 principal 인정, 슈퍼유저가 로그인을 접음, 라우터·include 단위 인정, `include_in_schema=False` 포함, 문서 경로·Mount 제외, 중첩 include 펼침(전체 경로), 위반 목록 전부 — `tests/core/test_access_policy.py`
- [x] **앱 단위** — 실제 앱이 가드 통과(`test_main_app_passes_the_access_policy_guard`), 조립 경로가 가드를 부른다(`test_main_refuses_to_start_when_a_view_declares_no_access_level` — 별도 프로세스)
- [x] **회귀** — 예시 정책 표 대조(`test_route_access_levels_match_the_policy_table`), 표에서 뽑은 401/403 실요청, 기존 소유권·슈퍼유저 테스트 전부 통과, OpenAPI 바이트 동일·기존 골든·계약 테스트 통과
- [x] **공통 게이트** — ruff check·format, mypy, `pytest -m "not mysql"`(작업 트리 + `.env` 없는 저장소 밖 클론), uvicorn 수명주기 3건(fakeredis TCP), `review_gate --fast`, alembic 변경 없음 — run-log
- [x] **fail-on-revert** — 변이마다 해당 테스트 실패(run-log)

## 4. 변경 이력

- v0.1 (2026-10-13): 최초 작성(명세 §1~§7).
