"""접근 수준을 선언하지 않은 라우트가 하나 섞인 앱 — 실제 조립(main.py)이 기동을 거부하는지 본다 (L6).

``main`` 을 import 하기 **전에** 기능 라우터에 선언 없는 라우트를 더한다. ``main`` 은 import 시점에
``AccessPolicyGuard().verify(app)`` 를 부르므로, 거부가 동작하면 이 모듈의 import 자체가 실패한다.
"""

import app.features.blog as blog


async def _undeclared() -> dict[str, bool]:
    return {"ok": True}


blog.router.add_api_route("/e2e-undeclared", _undeclared, methods=["GET"])

from main import app  # noqa: E402,F401 - 위 라우트가 들어간 뒤에 조립해야 한다
