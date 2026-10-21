"""처리기가 없는 예외를 내는 엔드포인트가 있는 앱 — 실제 uvicorn 에서 연결 유지·로그 1번을 본다 (integration-e2e ADR-016).

예외 처리기·미들웨어는 ``main._register_exception_handlers`` 를 그대로 쓴다(운영 앱과 같은 등록).
``tests/integration/test_uvicorn_lifecycle.py`` 가 ``uvicorn`` CLI 로 띄운다(``DEBUG=false``).
"""

from __future__ import annotations

from fastapi import FastAPI

import main

app = FastAPI()
main._register_exception_handlers(app)


@app.get("/bug")
async def bug() -> None:
    raise RuntimeError("intentional bug for integration-e2e ADR-016")


@app.get("/ok")
async def ok() -> dict[str, bool]:
    return {"ok": True}
