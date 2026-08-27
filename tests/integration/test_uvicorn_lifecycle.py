"""실제 uvicorn server process 의 기동·종료 로그를 검증한다 (F-029 · F-038 계열).

lifespan 을 직접 호출하는 테스트로는 이 계열 결함이 **보이지 않는다.** 문제가 사는
곳이 lifespan 바깥이기 때문이다 — uvicorn 이 lifespan 종료 **뒤에** 남기는 최종 로그,
프로세스 종료 훅, 신호 처리. 실제로 Round 12 이전의 391 passed 는 F-028~F-039 를 하나도
잡지 못했다.

그래서 여기서는 진짜 자식 프로세스를 띄우고, 병합된 단일 stream 에서 순서를 본다.

    정상 종료:      … 자원 해제 완료 → Application shutdown complete → listener stop 완료
    startup 실패:   RuntimeError 와 traceback 이 프로젝트 포맷으로 실제 출력된다

MySQL 은 필요 없다. ``DEBUG=false`` 면 startup 이 테이블 자동 생성을 건너뛰므로 DB 에
접속하지 않고 readiness 지점까지 간다.
"""

from __future__ import annotations

import os
import pathlib
import signal
import socket
import subprocess  # noqa: S404 - 하네스가 의도적으로 실제 서버 프로세스를 띄운다
import sys
import threading
import time

import pytest

from tests.integration.uvicorn_startup_failure_app import STARTUP_FAILURE_MESSAGE

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

# 서버가 준비됐다고 판단하는 표지. uvicorn 이 listen 을 시작한 뒤에만 출력한다.
READY_MARKER = "Uvicorn running on"

# CI 의 느린 머신을 감안한 여유값. 넘기면 강제 종료 fallback 으로 넘어가고, 그 사실이
# 테스트 결과에 그대로 드러난다(정상 종료 근거로 쓰지 않는다).
READY_TIMEOUT_SECONDS = 60.0
STOP_TIMEOUT_SECONDS = 30.0


def _free_port() -> int:
    """지금 비어 있는 로컬 포트를 받아온다. 고정 포트는 병렬 실행에서 충돌한다."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class ServerProcess:
    """자식 server process 하나의 수명과 출력을 관리한다.

    Windows/POSIX 분기를 **전부 이 클래스 안에 가둔다.** 테스트 본문에 분기가 새면
    한쪽 플랫폼에서만 맞는 단언이 조용히 생긴다.

    출력은 ``stderr=STDOUT`` 으로 **단일 pipe** 에 합친다. 두 pipe 로 받으면 순서
    검증이 불가능하다 — 우리가 보려는 것이 바로 그 순서다.
    """

    def __init__(self, argv: list[str], port: int) -> None:
        env = os.environ.copy()
        # 부모(pytest)는 pytest-env 로 DEBUG=true 를 쓴다. 그대로 물려주면 reloader 가
        # 붙어 server process 가 둘이 되고 startup 이 테이블을 자동 생성하려 든다.
        env.update(
            {
                "DEBUG": "false",
                "ENV": "test",
                "SERVER_HOST": "127.0.0.1",
                "SERVER_PORT": str(port),
                "PYTHONPATH": str(PROJECT_ROOT),
                # 자식 출력 인코딩을 UTF-8 로 못 박는다. 지정하지 않으면 Windows 가
                # 콘솔 코드페이지(cp949)로 쓰는데 아래에서 UTF-8 로 디코딩하므로,
                # 한글 로그가 대체문자가 되어 "이 줄이 있는가" 검증이 조용히 실패한다.
                "PYTHONIOENCODING": "utf-8",
            }
        )

        platform_kwargs: dict = {}
        if sys.platform == "win32":
            # CTRL_BREAK_EVENT 는 **프로세스 그룹**에 보낸다. 새 그룹으로 띄우지 않으면
            # 신호가 pytest 자신에게도 날아간다.
            platform_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            platform_kwargs["start_new_session"] = True

        self._proc = subprocess.Popen(  # noqa: S603
            argv,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **platform_kwargs,
        )
        self._lines: list[str] = []
        # pipe 를 읽어 두지 않으면 버퍼가 차는 순간 자식이 write 에서 멈춘다.
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        self.forced = False

    def _pump(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            self._lines.append(line.rstrip("\n"))

    @property
    def output(self) -> str:
        return "\n".join(self._lines)

    def wait_for_marker(self, marker: str, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(marker in line for line in self._lines):
                return True
            if self._proc.poll() is not None:
                return False  # 준비되기 전에 죽었다
            time.sleep(0.05)
        return False

    def stop_gracefully(self) -> int:
        """운영에서 쓰는 정상 종료 신호를 보낸다. Windows 는 CTRL_BREAK, POSIX 는 SIGTERM."""
        graceful = signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGTERM
        self._proc.send_signal(graceful)
        return self._reap(STOP_TIMEOUT_SECONDS)

    def wait_for_exit(self, timeout: float) -> int:
        return self._reap(timeout)

    def _reap(self, timeout: float) -> int:
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # 강제 종료는 **fallback 전용**이다. 이 사실을 남겨 두지 않으면 강제로 죽인
            # 것을 정상 종료의 근거로 잘못 쓰게 된다.
            self.forced = True
            self._proc.kill()
            self._proc.wait(timeout=timeout)
        self._reader.join(timeout=5.0)
        if self._proc.stdout is not None:
            self._proc.stdout.close()
        return int(self._proc.returncode)

    def close(self) -> None:
        if self._proc.poll() is None:  # pragma: no cover - 단언 실패로 빠져나갈 때만
            self.forced = True
            self._proc.kill()
            self._proc.wait(timeout=STOP_TIMEOUT_SECONDS)


@pytest.fixture
def server_process():
    """자식 서버를 띄우는 팩토리. 테스트가 어떻게 끝나든 프로세스를 남기지 않는다."""
    started: list[ServerProcess] = []

    def _start(argv: list[str]) -> ServerProcess:
        port = _free_port()
        proc = ServerProcess([sys.executable, *argv], port)
        started.append(proc)
        return proc

    yield _start

    for proc in started:
        proc.close()


def _line_index(output: str, needle: str) -> int:
    for index, line in enumerate(output.splitlines()):
        if needle in line:
            return index
    raise AssertionError(f"출력에 {needle!r} 이 없다.\n----- 실제 출력 -----\n{output}")


def test_normal_shutdown_flushes_every_stage_in_order(server_process):
    """정상 종료에서 앱 정리 → uvicorn 종료 → listener 정지가 **순서대로** 관측된다.

    이 순서가 계약의 전부다 (AR-008 / ADR-018 / ADR-022).

    - 앱 자원 정리가 uvicorn 의 shutdown 완료보다 **먼저** 끝난다. 뒤집히면 DB 를 쓰는
      주체가 남아 있는데 커넥션 풀을 닫은 것이다.
    - listener 정지가 **가장 마지막**이다. 먼저 멈추면 그 뒤 로그가 소비자 없는 큐에
      갇혀 사라진다 — F-029 의 증상이 정확히 그것이었다.
    """
    proc = server_process(["main.py"])
    assert proc.wait_for_marker(
        READY_MARKER, READY_TIMEOUT_SECONDS
    ), f"서버가 {READY_TIMEOUT_SECONDS:.0f}초 안에 기동하지 않았다.\n{proc.output}"

    returncode = proc.stop_gracefully()
    out = proc.output

    assert not proc.forced, (
        "정상 종료 신호로 끝나지 않아 강제 종료했다. 강제 종료를 정상 종료의 근거로 "
        f"쓸 수 없다 (exit={returncode}).\n{out}"
    )

    # uvicorn 로그가 앱과 같은 queue·포맷으로 나간다 (ADR-020, run_server 경로)
    assert "[app=uvicorn]" in out, f"uvicorn 로그가 프로젝트 포맷으로 나오지 않았다.\n{out}"

    # DEBUG=false 가 실제로 먹었는지 — reloader 가 붙으면 프로세스가 둘이 된다
    assert (
        "Started reloader process" not in out
    ), f"reloader 가 떴다. DEBUG=false 가 안 먹었다.\n{out}"
    assert out.count("Started server process") == 1, f"server process 가 하나가 아니다.\n{out}"
    assert "테이블 자동 생성 건너뜀" in out, f"운영 정책(자동 생성 안 함)이 관측되지 않았다.\n{out}"

    assert (
        _line_index(out, "[shutdown] 애플리케이션 요청 처리 자원 해제 완료")
        < _line_index(out, "Application shutdown complete")
        < _line_index(out, "[log-lifecycle] stop 완료")
    ), (
        "종료 순서가 계약과 다르다. 기대: 앱 자원 정리 완료 → uvicorn shutdown 완료 → "
        f"listener 정지.\n{out}"
    )


def test_startup_failure_still_reports_the_cause(server_process):
    """startup 이 실패해도 원인이 **실제로 출력된다** (F-029).

    이 테스트가 F-029 가 고쳐졌다는 유일한 증거다. 예전에는 DB 가 꺼진 채 서버를 띄우면
    오류 원인이 한 글자도 나오지 않았다 — lifespan 이 listener 를 먼저 멈춰, 그 뒤에
    uvicorn 이 남기는 traceback 이 소비자 없는 큐에 갇혔기 때문이다.

    정상 앱과 **같은 실행 경로**(`run_server()`)로 띄운다. 실패 앱만 따로 기동하면
    검증 대상인 배선을 비켜 간다.
    """
    proc = server_process(["-m", "tests.integration.uvicorn_startup_failure_app"])
    returncode = proc.wait_for_exit(READY_TIMEOUT_SECONDS)
    out = proc.output

    assert not proc.forced, f"실패 앱이 스스로 끝나지 않아 강제 종료했다.\n{out}"
    assert (
        returncode != 0
    ), f"startup 이 실패했는데 정상 종료 코드가 나왔다 (exit={returncode}).\n{out}"

    assert "[app=uvicorn]" in out, f"uvicorn 로그가 프로젝트 포맷으로 나오지 않았다.\n{out}"
    assert "Application startup failed" in out, f"startup 실패 자체가 보고되지 않았다.\n{out}"
    assert "RuntimeError" in out, f"예외 타입이 출력되지 않았다 — traceback 이 유실됐다.\n{out}"
    assert STARTUP_FAILURE_MESSAGE in out, f"예외 메시지가 출력되지 않았다.\n{out}"
    assert (
        "[log-lifecycle] stop 완료" in out
    ), f"실패 경로에서 listener 가 정지되지 않았다 — 꼬리 로그가 유실된다.\n{out}"
