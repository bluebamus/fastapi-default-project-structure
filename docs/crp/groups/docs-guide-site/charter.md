# Charter — docs-guide-site  (Charter v0.1 / 2026-10-22)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 라운드 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 1 | `docs/guides/index.html`, `docs/guides/assets/style.css` | 문서 | 생성 허브·공통 스타일 |
| 1 | `docs/guides/` 아래 getting-started·architecture·reference·features·development·operations, workflows 의 request-processing·authentication·sequence-diagrams | 문서 | 생성 HTML 19편 |
| 1 | `README.md`, `docs/guides/ARCHITECTURE.md`, `docs/crp/groups/docs-guide-review/residual-risk.md` | 문서 | 같은 사실·색인·이력만 |
| 1 | 기능 서비스 docstring 5개, `.env.example` 주석 | 코드 주석 | 동작 불변 |
| 1 | `tests/test_docs_guide_site.py`, `tests/test_docs_guides.py` | 테스트 | 문서 계약 |

## 2. 계약 (Contract)

- **코드가 정답이다.** 코드 동작은 바꾸지 않는다(docstring·주석·문서·테스트만).
- 같은 사실은 README·ARCHITECTURE·DEVELOPMENT·HTML 안내서와 같은 값.
- 저장소 격리 — 다른 저장소 이름·비교 표현 금지.
- HTML 은 `html.parser` 로 읽히고 줄 단위 서식·끝 개행. 커밋된 파일의 인덱스 EOL 은 LF 그대로.

## 3. 인수 기준

- [x] 지적 42건 전부 처리 — 지적과 다르게 고친 것은 근거와 함께 ledger 에 남긴다
- [x] 내용 계약 테스트가 생성 원본에서 실패하고 수정본에서 통과
- [x] `tests/test_doc*.py` 통과(`.env` 없는 클론), ruff check·format --check 통과
- [x] 링크·앵커 검사 broken 0(README `Argon2id` 오탐 1건 제외), 공통 결함 표지 0
