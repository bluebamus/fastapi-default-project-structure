# Ledger — service-hardening (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.
>
> "출처" 의 `R-xx` 는 2026-10-07 전체 검수 보고서(로컬 전용, 저장소에 커밋하지 않는 도구 산출물)의
> 지적 번호다. "제안 n" 은 2026-10-12 요청(REQ-001)의 항목 번호다.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | REQ-001-A — CI 는 락 불일치에서 실패해야 한다 | Fix | Fixed | 단계 A1 · `tests/test_ci_contract.py` | 출처: 제안 1. `uv sync --frozen` 은 락을 검사하지 않는데 `ci.yml` 주석은 "어긋나면 실패한다" 고 적었다 |
| F-002 | LOW | ADR-003 — 게이트 판정은 추적 파일만 본다 | Fix | Fixed | 단계 A1 · `review_gate.repo_files` + `tests/scripts/test_review_gate_tracked_files.py` | 출처: 제안 1. `review_gate.py` 가 `rglob` 으로 작업 트리를 훑어 추적되지 않은 로컬 파일까지 판정에 넣는다 |
| F-003 | MED | INV-1 — DSN 은 어떤 비밀번호에서도 깨지지 않는다 | Fix | Fixed | 단계 A2 · `config.mysql_url` + `tests/core/test_dsn.py` · `test_percent_in_url_survives_alembic_config` | 출처: R-10. f-string 조립이 `@ : / # % ?` 에서 깨진다. Redis URL 도 같다 |
| F-004 | MED | INV-2 — 잠금 읽기는 writer·read-only 거부 | Fix | Fixed | 단계 A3 · `router._is_locking_select` + `test_orm_locking_select_is_served_by_writer` · `test_orm_locking_select_is_denied`(라우터 on/off) | 출처: R-14. ORM `with_for_update()` 가 replica 로 가고 read-only 가드를 통과한다 |
| F-005 | LOW | INV-3 — 목록 정렬은 결정적이다 | Fix | Fixed | 단계 A3 · `BaseRepository._default_order` + `test_list_orders_newest_first_and_breaks_ties_by_pk` · `test_same_created_at_is_ordered_by_id` · `test_list_active_breaks_created_at_ties_by_id` | 출처: 검수 데이터 계층 Low("기본 목록 조회에 ORDER BY 가 없음"). `created_at desc` 단일 키 쿼리 5곳도 동률 순서가 비결정적 |
| F-006 | MED | INV-4 / ADR-006 — 신뢰 홉 밖의 헤더는 믿지 않는다 | Fix | Open | 단계 B1 | 출처: R-08. `X-Forwarded-For` 를 무조건 믿는다 |
| F-007 | MED | INV-4 — 500 도 접속 로그에 남는다 | Fix | Open | 단계 B2 | 출처: R-09 |
| F-008 | HIGH | INV-4 / C-8 — 민감 쿼리 값을 저장하지 않는다 | Fix | Open | 단계 B2 | 출처: R-02 일부(쿼리스트링 저장). 조회 API 보호는 F-023 |
| F-009 | MED | INV-4 — 길이 초과 값이 INSERT 를 실패시키지 않는다 | Fix | Open | 단계 B3 | 출처: R-08(길이). MySQL strict 에서 실패 후 조용히 버려진다 |
| F-010 | MED | ADR-008 ① — null PATCH 는 422 | Fix | Open | 단계 B4 | 출처: 제안 4·5 |
| F-011 | LOW | ADR-008 ② — DB 오류는 원인별 상태 코드 | Fix | Open | 단계 B5 | 출처: 검수 설계 Low("모든 IntegrityError 를 409 DUPLICATE 로 매핑") |
| F-012 | LOW | ADR-008 ③ — 리포트 날짜 범위 상한 | Fix | Open | 단계 B6 | 출처: 제안 5 |
| F-013 | LOW | ADR-008 ④ — 4xx 는 WARNING | Fix | Open | 단계 B7 | 출처: 검수 설계 Low("4xx 를 ERROR 레벨로 로깅") |
| F-014 | MED | ADR-009 — read-only override 는 read-only 로 표시된다 | Fix | Open | 단계 C1 | 출처: R-15 |
| F-015 | MED | ADR-009 — ORM 경로도 MySQL 에서 검증한다 | Fix | Open | 단계 C2 | 출처: R-16 |
| F-016 | HIGH | INV-5 — UTC·마이크로초 저장 | Fix | Open | 단계 D | 출처: R-05 |
| F-017 | MED | ADR-011 — Redis 는 필수이며 `/ready` 가 본다 | Fix | Open | 단계 E1 | 출처: R-13. 사용자 결정 "redis 필수" 로 지적의 전제(API 가 Redis 를 안 씀)를 해소한다 |
| F-018 | LOW | ADR-012 — 중앙 파일이 기능을 import 하지 않는다 | Fix | Open | 단계 E2 | 출처: 제안 8. `app/celery/tasks.py` 가 기능 태스크를 중앙 집중 |
| F-019 | MED | INV-6 — refresh 회전·재사용 탐지 | Fix | Open | 단계 F1 | 출처: R-11 |
| F-020 | MED | ADR-016 — 로그인 시도 제한 | Fix | Open | 단계 F1 | 출처: R-12 |
| F-021 | LOW | ADR-013 — 비밀번호가 조용히 잘리지 않는다 | Fix | Open | 단계 F1 | 출처: 검수 설계 Low("bcrypt 72바이트가 조용히 잘림") |
| F-022 | HIGH | INV-7 — 쓰기 경로는 인증·소유권을 요구한다 | Fix | Open | 단계 F2 | 출처: R-01 |
| F-023 | HIGH | INV-7 — 접속 로그 조회는 슈퍼유저 | Fix | Open | 단계 F2 | 출처: R-02 |
| F-024 | LOW | ADR-020 — 로그인 불가 계정을 만들지 않는다 | Fix | Open | 단계 F2 | 출처: 검수 설계 Low("/users POST 는 비밀번호 없이 생성") |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
