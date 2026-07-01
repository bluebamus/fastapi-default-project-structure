# docs/concepts — 개념 / 기술 심화 문서

이 폴더는 프로젝트의 **기술적 개념과 패턴을 깊이 있게 설명하는 휴먼 리딩용 문서**를
통합 저장하는 곳입니다. "왜 이렇게 동작하는가", "두 방식 중 무엇을 언제 쓰는가"
같은, 코드만으로는 드러나지 않는 설계 의도와 배경 지식을 다룹니다.

> 비교 대상 — [`../ARCHITECTURE.md`](../ARCHITECTURE.md)(공식 구조 SSOT),
> `../refactoring/`(변경 기록). 이 폴더는 그중 **개념 설명/심화 해설** 담당입니다.

> ⚠️ **DEPRECATED 알림 (2026-07-01):** 아래 `app-registration-installed-apps`,
> `auto-discovery-registry` 문서는 **현재 코드에 없는 등록 메커니즘**(`app/apps.py` 수동 등록,
> `AppRegistry` 자동발견)을 설명합니다. 프로젝트는 표준 FastAPI 배선(각 앱 `__init__.py`가 `router`
> 공개 → `main.py`의 `APPS`가 `include_router`로 취합)으로 전환되었습니다. 두 문서는 **역사적 기록**으로만
> 참고하세요. 현행 구조는 [`../ARCHITECTURE.md`](../ARCHITECTURE.md)가 SSOT입니다.
> (`session-management-patterns`의 UnitOfWork 컨텍스트 매니저 예시도 현재는 미사용 — 세션은 의존성이 관리.)

## 문서 작성 규칙

- **파일명:** `<주제-슬러그>-<YYYY-MM-DD>.md` (생성 날짜를 파일명 뒤에 부착)
- **쌍둥이 산출물:** 같은 내용을 `.md`(텍스트/링크)와 `.html`(도식·스타일)로 함께 작성
- **도식화:** Mermaid 다이어그램 + ASCII 그림으로 흐름을 시각화
- **서술:** 초심자도 따라올 수 있는 친절하고 자세한 내러티브 설명
- **단일 진실 소스:** 코드와 문서가 다르면 코드가 정답 — 문서를 갱신

## 문서 목록

| 문서 | 작성일 | 요약 |
|------|--------|------|
| [session-management-patterns](session-management-patterns-2026-06-23.md) ([HTML](session-management-patterns-2026-06-23.html)) | 2026-06-23 | DB 세션 관리의 두 패턴 — AsyncGenerator(`yield`) vs Context Manager(`UnitOfWork`) 비교와 선택 가이드 |
| [app-registration-installed-apps](app-registration-installed-apps-2026-06-25.html) (HTML) | 2026-06-25 | 🗑️ **DEPRECATED** — `app/apps.py` 수동 등록(Django `INSTALLED_APPS` 대응) 설명. 해당 메커니즘은 2026-07-01 제거됨(현재 표준 `include_router` 배선). 역사적 기록. |
| [auto-discovery-registry](auto-discovery-registry-2026-06-25.html) (HTML) | 2026-06-25 | 🗑️ **DEPRECATED** — 자동발견(`AppConfig`/`AppRegistry`) 설계 분석. 해당 브랜치·메커니즘 모두 제거됨(2026-07-01). 역사적 기록. |
