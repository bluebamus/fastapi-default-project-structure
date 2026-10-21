# Design Baseline — docs-guide-review (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태(Active/Superseded)만 바꾼다.
>
> **ID 범위:** `REQ-0xx`·`ADR-0xx` 는 **이 그룹 안에서만** 번호를 매긴다. 지적 ID(F01~F29·M1~M5)는 검수 보고의 번호를 그대로 쓴다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [ ] **보통(Balanced)**
- [x] **간략(Lean)** — 사용자가 범위를 정해 승인했다. 지적이 코드와 어긋나면 고치지 않고 보고한다.

선택: **간략** · 선택일: 2026-10-21 · 변경 이력: (없음)

## 1. 목적 / 배경

`docs/guides/` 6개 문서를 코드(main `6eff7a2`)와 대조한 검수 보고가 29건(HIGH 2 · MED 9 · LOW 18)과 누락 5건을 냈다.
코드는 그대로 두고 문서를 코드에 맞춘다. README 에 같은 사실이 틀리게 적힌 곳도 함께 고친다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-21 | "88건 모두 수정하고 README 도 같이 고쳐줘" (이 저장소 몫 29건 + 누락 표) | 지적 전부를 코드 근거를 다시 열어 확인한 뒤 고친다. README 는 같은 사실만 맞춘다. 줄 번호 근거는 현재 줄 또는 함수 이름으로. HTML 기준일·기준 커밋 갱신 | Active | ADR-001, ledger 전체 |

## 3. 설계 결정 (append-only)

| ADR-ID | 날짜 | 결정 | 상태 |
|---|---|---|---|
| ADR-001 | 2026-10-21 | **근거는 이름으로.** 고친 문장의 코드 근거는 줄 번호 대신 함수·클래스 이름(`_register_exception_handlers`·`entry_process`·`DatabaseErrorTranslator`·`_retry_unreachable_replica_on_writer` 등)으로 적는다 — 줄 번호는 다음 변경에서 깨진다. HTML 기준은 브랜치가 아니라 main 커밋 | Active |

## 4. 불가침 제약

- C-1: 코드·테스트 동작 불변(문서 계약 테스트 기대값 갱신만 허용 — 이번에는 필요 없었다).
- C-2: `docs/review/` 는 커밋하지 않는다.

## 5. 변경 이력

| 날짜 | 변경 |
|---|---|
| 2026-10-21 | 그룹 개설(REQ-001, ADR-001), 브랜치 `docs/guide-fixes` |
