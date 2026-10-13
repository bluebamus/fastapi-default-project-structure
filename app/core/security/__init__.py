"""인증·인가 공용 부품 (service-hardening ADR-013~018·ADR-026).

토큰 발급·검증(``TokenService``), refresh 회전 기록(``RefreshTokenStore``), 고정 창 레이트 리밋
(``RateLimiter``), 비밀번호 해시(``PasswordHasher``), 인증 주체(``Principal``)와 소유권 규칙
(``OwnershipPolicy``), 그리고 이들을 만드는 provider·``get_current_principal``·``require_superuser``
(``dependencies``), 뷰 단위 접근 수준 선언과 기동 시 기본 거부 검사(``access``). 여러 기능이
쓰므로 core 에 둔다 — 기능끼리 import 하지 않는 규칙(C-2)을 지키는 유일한 위치다.
각 클래스는 협력 객체(설정·Redis 클라이언트)를 생성자로 받고, 조립은 provider 함수가 한다(C-1).
"""
