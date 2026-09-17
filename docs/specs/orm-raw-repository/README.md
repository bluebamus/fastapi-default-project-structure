# ORM/Raw Repository 설계 명세

ORM(`BaseRepository`)과 Raw SQL(`RawRepositoryBase`) 이중 데이터 접근 구조를 만들 때 확정한
**원본 명세 3종**이다. 2026-08-13에 작성했고, 2026-09-17에 날짜 이름 폴더
(`docs/orm-raw-repository/2026-08-13/`)에서 이 폴더로 옮겨 git 추적 대상으로 되돌렸다.
날짜 이름 폴더는 `.gitignore` 가 로컬 작업 기록으로 취급해 저장소에서 제외한다.

| 문서 | 내용 | 참조하는 곳 |
|---|---|---|
| [`requirements.md`](requirements.md) | 요구 명세 — 요구 ID(REQ·NFR·SCN 등)의 원본 | `scripts/review_gate.py` 의 요구 ID 실재 검사, CRP design-baseline |
| [`development-plan.md`](development-plan.md) | 설계·실행 순서 (Phase 0~7) | CRP charter·design-baseline, 코드 주석의 `development-plan §` |
| [`workflow-guide.md`](workflow-guide.md) | 구현 지침·예시 코드 | 코드 주석의 `workflow-guide §` |

- 이 문서들은 **착수 시점의 기준선**이다. 현재 코드의 사용법은 [`../../guides/`](../../guides/) 를 본다.
- 결정의 근거와 이후 변경 이력은 [`../../crp/groups/orm-raw-repository/`](../../crp/groups/orm-raw-repository/) 에 있다.
- 파일을 옮기거나 이름을 바꾸면 `scripts/review_gate.py` 의 요구 ID 검사 경로도 함께 고친다.
