"""인증 공용 부품 (service-hardening ADR-014~016).

토큰 발급·검증(``TokenService``), refresh 회전 기록(``RefreshTokenStore``), 고정 창 레이트
리밋(``RateLimiter``). 발급은 auth 기능이 하지만 검증은 다른 기능의 의존성도 쓰므로 core 에
둔다 — 기능끼리 import 하지 않는 규칙(C-2)을 지키는 유일한 위치다. 각 클래스는 협력 객체
(설정·Redis 클라이언트)를 생성자로 받고, 조립은 auth 기능의 provider 함수가 한다(C-1).
"""
