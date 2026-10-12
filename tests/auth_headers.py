"""엔드포인트 테스트의 인증 헤더 — 실제 ``TokenService`` 로 발급한 access 토큰 (service-hardening ADR-017).

의존성을 가짜로 바꾸지 않고 진짜 토큰을 싣는다. 그래야 라우트의 인증 경로(``OAuth2PasswordBearer`` →
``TokenService.decode`` → ``Principal``)가 테스트에서도 그대로 돈다. 인가와 무관한 CRUD 테스트는
``SUPERUSER`` 헤더를 클라이언트 기본값으로 둔다 — 슈퍼유저는 소유권·관리 경로 검사를 통과한다.
"""

from __future__ import annotations

from app.core.security.authorization import Principal
from app.core.security.dependencies import get_token_service

SUPERUSER = Principal(
    id="00000000-0000-4000-8000-00000000a001", username="admin", is_superuser=True
)
ALICE = Principal(id="00000000-0000-4000-8000-0000000a11ce", username="alice", is_superuser=False)
BOB = Principal(id="00000000-0000-4000-8000-000000000b0b", username="bob", is_superuser=False)


def bearer(principal: Principal = SUPERUSER) -> dict[str, str]:
    """``principal`` 의 access 토큰을 담은 ``Authorization`` 헤더."""
    issued = get_token_service().issue_access(
        principal.id, principal.username, principal.is_superuser
    )
    return {"Authorization": f"Bearer {issued.token}"}
