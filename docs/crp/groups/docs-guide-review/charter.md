# Charter — docs-guide-review  (Charter v0.1 / 2026-10-21)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 라운드 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 1 | `docs/guides/index.html` | 문서 | 지적 0 — 확인만 |
| 1 | `docs/guides/ARCHITECTURE.md`, `docs/guides/DEVELOPMENT.md` | 문서 | |
| 1 | `docs/guides/workflows/server-lifecycle.html`·`feature-development.html`·`admin-authentication.html` | 문서 | |
| 1 | `README.md` | 문서 | 지적과 **같은 사실**만 — 새 종류의 검수는 하지 않는다 |

## 2. 계약 (Contract)

- **코드가 정답이다.** 문서만 고친다. 코드·테스트 동작은 바꾸지 않는다.
- 같은 사실이 여러 문서에 있으면 모두 같은 값으로 맞춘다.
- 저장소 격리 — 다른 저장소를 언급·비교하지 않는다.
- 줄바꿈 보존 — main 대비 EOL 이 바뀐 파일 0.

## 3. 인수 기준

- [x] 지적 29건(F01~F29)과 누락 5건(M1~M5) 전부 처리 — 고치지 않은 것은 근거와 함께 ledger 에 남긴다
- [x] `tests/test_docs_guides.py`·`tests/test_docs_secret_examples.py` 통과
- [x] 링크·앵커 검사 broken 0(README `pwdlib[argon2](Argon2id)` 오탐 1건 제외)
- [x] HTML 4편 `html.parser` 태그 불일치 0
- [x] `git diff --ignore-cr-at-eol --stat` 이 `git diff --stat` 과 같다(EOL 변화 0)
