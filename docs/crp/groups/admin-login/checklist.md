# Checklist — admin-login (개선 항목 추적판)

> 모든 개선 사항은 여기서 추적된다. 각 항목이 닫히기(`[x]`) 전엔 "완료" 가 아니다. ledger 의 Fix 와 1:1 로 연결한다.

## Round 1 — 2026-10-12 · 원 명세 (관리 화면 로그인 · Bootstrap 화면 · 배포 전 할 일 · Celery include)
- [x] 요청을 design-baseline §2 에 기록 + 이전 요구 충돌 확인(`service-hardening` C-9·ADR-019, `orm-raw-repository` C-8·ADR-045 ③ → ADR-004)
- [x] 의존성 `itsdangerous`(ADR-002)
- [x] (F-001) `AdminAuthBackend` + `build_admin_auth_backend` + `create_admin_interface` 주입 + 단위·화면·통합·`mysql` 마커 테스트
- [x] Bootstrap 로그인 템플릿(5.3.8, SRI 실측) — 로더 우선순위 코드로 확인(ADR-003)
- [x] `ADMIN_ALLOW_UNAUTHENTICATED`·배포 검사 규칙·기동 WARNING 제거 + 회귀 테스트
- [x] (F-002) Celery include import 테스트
- [x] (F-004) 배포 전 할 일 4개 — README·`.env.example`·config·docstring
- [x] 실기동 스모크(uvicorn·SQLite·fakeredis TCP·curl)

## Round 2 — 2026-10-12 · 추가 명세 (ADMIN_DISABLED · 세션 범위 · 안내서 · 모든 문서)
- [x] (F-003) `ADMIN` → `ADMIN_DISABLED` + 예전 이름 잔존 거부 + 끈 상태 4가지 보장 테스트
- [x] 세션 범위 확인(감독자 가정과 코드 일치) + 테스트 4건(ADR-006)
- [x] `docs/guides/workflows/admin-authentication.html`(12절, Mermaid 도식 8개) + README 문서 표·ARCHITECTURE §12 링크
- [x] 모든 문서 반영(README·`.env.example`·ARCHITECTURE·DEVELOPMENT·HTML 2편·CRP 상태 줄) + 낡은 서술 grep
- [x] 공통 게이트 그린 · fail-on-revert 23/23 · run-log 갱신

## Round 3 — 2026-10-12 · 감독자 확인 지시 (ModelView 필터)
- [x] 결함 재현(로그인 후 목록 화면 `AttributeError: ... 'parameter_name'`) → (F-005) `sqladmin.filters` 로 교체, 생성 시각 필터 제외(ADR-009)
- [x] `tests/test_admin_views_render.py` — 모든 뷰 목록·필터·상세 1건 200 + 정의 검사, fail-on-revert 3/3
- [x] 실기동 스모크에서 목록 7개·필터 3건 200 · 안내서·ARCHITECTURE·DEVELOPMENT 에 규칙 기록

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
