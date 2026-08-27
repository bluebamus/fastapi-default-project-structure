# 검증 보고서 — Round 11

| 항목 | 값 |
|---|---|
| 작성일 | 2026-08-25 |
| 대상 | ADR-016 리팩터 + F-026 수정 |
| 판정 | **CONVERGED** — Open Fix 0 · 요구사항 회귀 0 |
| 환경 | Python 3.14.4 · Windows(개발) · MySQL 8.4 컨테이너(호스트 포트 3308) |

> 이 문서에 적힌 수치는 전부 **이번 세션에서 실제로 실행해 얻은 값**이다.
> 실행하지 않은 것은 §4 에 따로 적었다.

---

## 1. 테스트

| 실행 | 결과 |
|---|---|
| `tests/core/test_resources.py` (리팩터 직후) | **13 passed** — 파일 수정 없음 |
| 전체 (MySQL 컨테이너 없음) | 383 passed, **8 skipped** |
| 전체 (MySQL 8.4 기동 후) | **391 passed, 0 skipped** |

### skipped 8건에 대해 — 중요

첫 전체 실행은 `383 passed, 8 skipped` 였다. 이 상태로 "전건 통과"라고 적었다면
**MySQL 통합 8건을 건너뛴 채 초록으로 보였을 것이다.** residual-risk **R-003** 이 경고하는
바로 그 상황이다("실행 안 된 것이 초록으로 보인다").

```bash
docker compose -f compose.test.yaml up -d     # MySQL 8.4, 호스트 포트 3308
# healthcheck 가 healthy 가 될 때까지 대기 (약 11회 폴링)
python -m pytest -q                            # → 391 passed, 0 skipped
docker compose -f compose.test.yaml down -v    # 정리
```

결과 줄의 `skipped` 개수를 보지 않으면 눈치챌 수 없다. 이번엔 컨테이너를 올리고
재실행해 **skipped 0** 을 확인했다.

---

## 2. 검수 게이트

`scripts/review_gate.py` — 코드 변경 후 1회, 문서 변경 후 1회, 총 **2회 전건 통과**.

| # | 검사 | 결과 |
|---|---|---|
| 1 | pytest | PASS |
| 2 | ruff check | PASS |
| 3 | ruff format --check | PASS |
| 4 | mypy | PASS |
| 5 | INV-1 View 가 SQL/세션을 직접 다루지 않음 | PASS |
| 6 | INV-2 Repository/Dependency commit 없음 | PASS |
| 7 | INV-5 Raw Base 가 ORM Base 를 상속하지 않음 | PASS |
| 8 | INV-11 기존 공개 API 불변 | PASS — 제거됨 0 · 상태코드변경 0 |
| 9 | MySQL 테스트 포트 단일 출처 (ADR-008) | PASS |
| 10 | 문서 인용 커밋 도달성 (ADR-009) | PASS — 검사 22건 |
| 11 | 인용 요구 ID 실재 (ADR-014) | PASS — 선언 **73 → 75건** |
| 12 | INV-10 path operation async + 동기 I/O 부재 | PASS — 검사 36건 |
| 13 | charter 인수기준 ↔ 수렴 선언 정합 (ADR-015) | PASS — 열린 칸 0 · 수렴선언 True |

> 표의 13행은 게이트가 보고하는 **검사 11종**을 펼친 것이다(1~4 는 정적 게이트 4종).

**검사 11의 선언 ID 가 73 → 75 로 늘어난 것**이 REQ-007·ADR-016 이 design-baseline 에
정식 등록됐다는 기계 확인이다. 인용만 있고 선언이 없으면 이 검사가 빨개진다(F-022 재발 방지).

---

## 3. 실행 실측 — 실제 앱 기동·종료

`main.app` 의 lifespan 을 열고 닫아 관측했다. 단위 테스트가 아니라 **실물 앱**이다.

### 리팩터 전

```text
[shutdown] 애플리케이션 자원 해제 시작
[shutdown] background task 정리 완료 (0.0ms)
[dispose_engine] Disposing database engines...
[dispose_engine] Main engine disposed
[dispose_engine] Background engine disposed - ALL DONE
[shutdown] DB engine 정리 완료 (0.4ms)
                            ← "해제 완료" 줄이 없다 (F-026)
```

### 리팩터 후

```text
[shutdown] 애플리케이션 자원 해제 시작
[shutdown] background task 정리 완료 (0.0ms)
[dispose_engine] Disposing database engines...
[dispose_engine] Main engine disposed
[dispose_engine] Background engine disposed - ALL DONE
[shutdown] DB engine 정리 완료 (0.4ms)
[shutdown] 애플리케이션 자원 해제 완료      ← 살아났다
```

두 경우 모두 실행 순서는 동일했다.

| 관측 항목 | 리팩터 전 | 리팩터 후 |
|---|---|---|
| 해제 순서 | drain → dispose → listener stop | 동일 |
| `dispose_engine` 실제 호출 | O (`ALL DONE`) | O (`ALL DONE`) |
| 종료 후 `app.state.resources` | `None` | `None` |
| 종료 완료 로그 | **출력 안 됨** | 출력됨 |

---

## 4. 요구사항 회귀 점검

design-baseline §4 의 불가침 제약 **C-1 ~ C-9** 위반 없음.

| 제약 | 확인 방법 |
|---|---|
| C-1 공개 API 불변 | 게이트 검사 8 (INV-11) — 제거 0 · 상태코드변경 0 |
| C-6 shutdown 에서 table drop 금지 | 종료 경로에 DDL 없음 — 실측 로그로 확인 |
| C-7 3306 공유 인스턴스 무접촉 | 기동한 것은 **3308 전용 컨테이너뿐**이고 `down -v` 로 정리. 정리 후 `docker ps` 에 MySQL 컨테이너 없음 |

나머지 제약(C-2~C-5, C-8, C-9)은 이번 변경이 건드리지 않는 영역이다.

**AR-008 확인**: 수용 기준이 "startup 전체가 `try/finally` **또는** 동등한 async context
manager cleanup 으로 보호된다"이므로, 이번 전환은 요구 위반이 아니라 **첫 번째 허용
형태로의 이동**이다.

---

## 5. 검사하지 않은 것 (정직한 범위 표시)

- **부하 상황의 종료**: in-flight 태스크가 실제로 drain timeout 을 넘기는 상황을 부하로
  재현하지 않았다. 해당 경로는 단위 테스트(`test_cancelled_task_cleanup_survives_the_outer_timeout`)로만 검증했다.
- **SIGTERM 실경로**: uvicorn 프로세스에 실제 시그널을 보내 종료시키지 않았다.
  lifespan 컨텍스트를 직접 열고 닫아 관측했다.
- **Celery worker 종료**: 이번 변경 범위 밖이며 워커를 기동하지 않았다(기존 residual-risk 와 동일).
- **다중 worker 환경**: worker 별 pool 이 각각 해제되는지는 단일 프로세스로만 확인했다.

이 목록은 `docs/crp/groups/orm-raw-repository/residual-risk.md` 하단의 기존 미검사 항목과
별개로, **이번 라운드가** 확인하지 않은 것이다.
