# docs/concepts — 개념 / 기술 심화 문서

이 폴더는 프로젝트의 **기술적 개념과 패턴을 깊이 있게 설명하는 휴먼 리딩용 문서**를
통합 저장하는 곳입니다. "왜 이렇게 동작하는가", "두 방식 중 무엇을 언제 쓰는가"
같은, 코드만으로는 드러나지 않는 설계 의도와 배경 지식을 다룹니다.

> 비교 대상 폴더 — `architecture/`(공식 구조), `refactoring/`(변경 기록),
> `design-pattern/`(패턴 카탈로그). 이 폴더는 그중 **개념 설명/심화 해설** 담당입니다.

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
