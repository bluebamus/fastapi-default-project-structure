"""startup 이 반드시 실패하는 FastAPI 앱 — 실패 경로의 로그를 실물로 검증하기 위한 것.

두 가지를 **정상 앱과 똑같이** 맞춘다. 하나라도 어긋나면 검증 대상이 아니라 하네스를
시험하게 된다.

1. 실행 경로: `main.run_server()` 로 띄운다 (프로젝트 log_config 연결, 프로세스 종료 훅).
2. 자원 관리 경로: **실제 `manage_application_resources()` 안에서** 실패한다.
   바깥에서 그냥 `raise` 하면 자원 관리자의 정리 코드가 돌지 않아, F-029 가 살아 있어도
   traceback 이 멀쩡히 출력된다 — 잡으려는 결함을 비켜 가는 테스트가 된다.
   F-029 는 *정리 과정이 listener 를 멈춘 탓에 그 뒤 traceback 이 사라지는* 결함이었다.

`tests/integration/test_uvicorn_lifecycle.py` 가 자식 프로세스로 띄운다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.resources import manage_application_resources

STARTUP_FAILURE_MESSAGE = "intentional startup failure F-029"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """자원을 정상적으로 올린 **뒤** 실패한다.

    DB 는 필요 없다. ``DEBUG=false`` 면 자원 관리자가 테이블 자동 생성을 건너뛰므로
    접속 없이 여기까지 온다.
    """
    async with manage_application_resources(app):
        raise RuntimeError(STARTUP_FAILURE_MESSAGE)
        yield  # pragma: no cover - 도달하지 않는다. asynccontextmanager 계약상 필요하다.


app = FastAPI(lifespan=lifespan)


if __name__ == "__main__":
    from main import run_server

    run_server("tests.integration.uvicorn_startup_failure_app:app")
