"""app/utils/logs 로깅 서브시스템 테스트.

검증: appname 산출, 클래스명 자동추출(A), 믹스인 주입(C), 포맷 필드, end-to-end.
"""

import io
import logging
import os
import pathlib
import queue
import subprocess  # noqa: S404 - 테스트 하네스가 의도적으로 자식 프로세스를 띄운다
import sys
import threading
import time
import types

import pytest

from app.utils.logs import (
    LOG_FORMAT,
    ContextFilter,
    LoggerMixin,
    TzFormatter,
    get_logger,
    setup_uvicorn_logging,
)
from app.utils.logs import config as logs_config
from app.utils.logs import queue_handler as logs_queue
from app.utils.logs import setup as logs_setup
from app.utils.logs.filters import _app_from_path


def _rec(pathname="/x/app/features/blog/services/item_service.py", func="create"):
    return logging.LogRecord("blog", logging.INFO, pathname, 10, "hello", (), None, func)


def test_appname_from_path():
    assert _app_from_path("/x/app/features/blog/services/item_service.py") == "blog"
    assert _app_from_path("C:\\x\\app\\core\\bootstrap.py") == "core"
    assert _app_from_path("/x/app/celery/tasks.py") == "celery"
    assert _app_from_path("/x/app/utils/pagination/paginator.py") == "utils"
    assert _app_from_path("/x/migrations/env.py") == "migrations"


def test_repo_root_modules_are_not_labeled_external():
    """저장소 루트의 모듈이 'ext'(서드파티)로 분류되면 안 된다 (LOG-2).

    ``main.py``·``config.py`` 는 경로에 ``/app/`` 조각이 없어서, 예전 판별식에서
    서드파티로 빠졌다. 그러면 appname 으로 '우리 코드'를 거를 수 없다.
    이 테스트는 ``filters.py`` 가 다른 깊이로 옮겨져 ``_REPO_ROOT`` 계산이
    어긋나는 경우도 함께 잡는다.
    """
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    for name in ("main.py", "config.py"):
        assert (repo_root / name).is_file(), f"{name} 이 저장소 루트에 없다 — 테스트 전제 붕괴"
        assert _app_from_path(str(repo_root / name)) == "app"


def test_installed_packages_are_external():
    """저장소 루트 **안**의 .venv 도 서드파티로 분류된다."""
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    vendored = repo_root / ".venv" / "Lib" / "site-packages" / "sqlalchemy" / "engine.py"
    assert _app_from_path(str(vendored)) == "ext"
    assert _app_from_path("/opt/py/lib/python3.14/site-packages/httpx/_client.py") == "ext"


class _Caller:
    def run(self) -> str:
        rec = _rec()
        ContextFilter().filter(rec)
        return rec.classname


def test_classname_extracted_from_calling_class():
    """방식 A — 호출 클래스의 메서드에서 자동으로 클래스명을 채운다."""
    assert _Caller().run() == "_Caller"


def test_classname_dash_for_free_function():
    rec = _rec()
    ContextFilter().filter(rec)  # 모듈 레벨 호출(self 없음)
    assert rec.classname == "-"


def test_mixin_injects_classname():
    """방식 C — LoggerMixin 이 classname 을 extra 로 주입."""

    class _Svc(LoggerMixin):
        pass

    assert _Svc().log.extra["classname"] == "_Svc"


def test_format_contains_all_fields():
    rec = _rec()
    rec.appname = "blog"
    rec.classname = "ItemService"
    out = TzFormatter(LOG_FORMAT).format(rec)
    assert "app=blog" in out
    assert "item_service:ItemService:create:10" in out
    assert ("KST" in out) or ("UTC" in out)


def test_get_logger_end_to_end():
    logger = get_logger("test.e2e")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.addFilter(ContextFilter())
    handler.setFormatter(TzFormatter(LOG_FORMAT))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("hello world")
    finally:
        logger.removeHandler(handler)
    text = buf.getvalue()
    assert "hello world" in text
    assert "app=" in text


# =============================================================================
# 환경별 dictConfig 구성
#
# staging/production 가지는 로컬·CI 에서 실행되지 않는다 — 즉 운영에서 처음 도는
# 코드다. dictConfig 를 실제로 **적용하지 않고** 빌더가 만든 dict 만 검사하므로
# 핸들러도 listener 스레드도 만들어지지 않는다(부작용 없음).
# =============================================================================
def _build_with(monkeypatch, tmp_path, **overrides):
    """ENV·로그 설정을 바꿔 build_dictconfig() 결과를 얻는다.

    빌더가 모듈 전역 settings 를 읽으므로 그 속성을 monkeypatch 로 갈아끼운다
    (monkeypatch 가 테스트 종료 시 되돌린다 — 싱글턴 오염 없음).
    """
    env = overrides.pop("env", "development")
    monkeypatch.setattr(logs_config.app_settings, "ENV", env, raising=False)
    for key, value in overrides.items():
        monkeypatch.setattr(logs_config.log_settings, key, value, raising=False)
    return logs_config.build_dictconfig()


def test_root_uses_queue_handler_only(monkeypatch, tmp_path):
    """root 에는 queue 핸들러 하나만 붙는다 (NFR-009).

    요청 event loop 에서 동기 write/flush 가 일어나지 않으려면 root 에 출력
    핸들러가 직접 붙어서는 안 된다. stdout/stderr 쓰기는 listener 스레드의 몫이다.
    """
    for env in ("development", "test", "staging", "production"):
        cfg = _build_with(monkeypatch, tmp_path, env=env)
        assert cfg["root"]["handlers"] == [
            "queue"
        ], f"ENV={env} 의 root 에 queue 외 핸들러가 붙었다 — event loop 를 막는다"
        queue_handler = cfg["handlers"]["queue"]
        # dictConfig 네이티브 경로를 타려면 ``class`` 여야 한다 (ADR-021).
        # 선언 세부는 test_dictconfig_declares_the_queue_listener_natively 가 본다.
        assert queue_handler["class"] == "app.utils.logs.queue_handler.BoundedQueueHandler"
        # 컨텍스트는 **적재 전** 요청 스레드에서 채워야 classname 이 살아 있다.
        # sql_noise 는 SQL 본문·바인딩 파라미터 유출을 막는다(NFR-001).
        assert queue_handler["filters"] == ["sql_noise", "context"]


def test_no_file_handlers_in_any_environment(monkeypatch, tmp_path):
    """어느 환경에도 애플리케이션 파일 핸들러를 만들지 않는다 (NFR-009).

    저장·rotation 은 Docker/Kubernetes/운영 agent 가 담당한다. 파일 핸들러가
    다시 생기면 요청 스레드가 동기 rotation 을 수행하게 되므로 이 테스트가 관문이다.
    """
    for env in ("development", "test", "staging", "production"):
        cfg = _build_with(monkeypatch, tmp_path, env=env)
        for name, handler in cfg["handlers"].items():
            assert "File" not in handler.get(
                "class", ""
            ), f"ENV={env} 에 파일 핸들러 {name} 이 생겼다"


def test_production_separates_errors_to_stderr(monkeypatch, tmp_path):
    """production/staging 은 stdout 에 더해 ERROR 전용 stderr 출력을 갖고 UTC 를 쓴다."""
    for env in ("production", "staging"):
        cfg = _build_with(monkeypatch, tmp_path, env=env)

        assert set(cfg["handlers"]) == {"queue", "console", "error_console"}
        assert cfg["formatters"]["app"]["use_utc"] is True

        assert cfg["handlers"]["console"]["stream"] == "ext://sys.stdout"
        assert cfg["handlers"]["error_console"]["stream"] == "ext://sys.stderr"
        assert cfg["handlers"]["error_console"]["level"] == "ERROR"

        # listener 가 두 출력 모두를 위임받아야 한다.
        assert logs_config.listener_handler_names(env) == ["console", "error_console"]


def test_development_is_stdout_only_and_local_time(monkeypatch, tmp_path):
    """개발에서는 stdout 하나만 쓰고 로컬 TZ + 밀리초를 쓴다."""
    cfg = _build_with(monkeypatch, tmp_path, env="development")

    assert set(cfg["handlers"]) == {"queue", "console"}
    assert cfg["formatters"]["app"]["use_utc"] is False
    assert cfg["formatters"]["app"]["with_ms"] is True
    assert logs_config.listener_handler_names("development") == ["console"]


def test_dictconfig_has_no_per_app_loggers(monkeypatch, tmp_path):
    """앱 dictConfig 에 앱별 로거를 **등록하지 않는다**(핸들러는 root 에만).

    이 프로젝트는 Django 의 ``settings.LOGGING["loggers"]`` 식 등록을 쓰지 않고
    소스 경로에서 앱을 판별한다. ``loggers`` 키가 생기면 그 설계가 바뀐 것이므로,
    코드보다 charter §2-4 비목표를 먼저 고쳐야 한다. 이 테스트가 그 관문이다.

    uvicorn 3종 로거는 여기서 걸리지 않는다 — ``setup_uvicorn_logging()`` 이 만들어
    ``uvicorn.run(log_config=...)`` 으로 **uvicorn 에게 넘기는 별도 설정**이고, 앱
    ``build_dictconfig()`` 에는 들어가지 않는다 (ADR-020).
    """
    for env in ("development", "test", "staging", "production"):
        cfg = _build_with(monkeypatch, tmp_path, env=env)
        assert "loggers" not in cfg, (
            f"ENV={env} 의 dictConfig 에 loggers 키가 생겼습니다. "
            "앱별 로거 등록은 charter §2-4 의 비목표입니다 — 코드보다 그 조항을 먼저 "
            "개정하세요. uvicorn 로거가 필요하면 setup_uvicorn_logging() 쪽입니다(ADR-020)."
        )
        assert cfg["root"]["handlers"], "root 에 핸들러가 없으면 아무 로그도 나가지 않는다"


def test_uvicorn_shares_the_app_queue(monkeypatch):
    """uvicorn 3종 로거가 앱과 **같은** queue 로 나가고 root 로 전파하지 않는다.

    propagate=True 면 앱 root 핸들러가 같은 줄을 한 번 더 찍어 중복 출력이 된다.
    핸들러는 앱과 공유하므로 ``app=uvicorn`` 라벨은 **로거** 필터로 찍어야 한다 —
    공유 핸들러에 붙이면 앱 로그까지 uvicorn 으로 라벨링된다.
    """
    cfg = setup_uvicorn_logging()

    assert set(cfg["loggers"]) == {"uvicorn", "uvicorn.error", "uvicorn.access"}
    for name, spec in cfg["loggers"].items():
        assert spec["propagate"] is False, f"{name} 이 root 로 전파되면 로그가 중복된다"
        assert spec["handlers"] == ["queue"], f"{name} 이 공유 queue 를 쓰지 않는다"
        assert spec["filters"] == ["uvicorn_app"], f"{name} 의 app 라벨 필터가 없다"

    assert cfg["handlers"]["queue"]["()"] == "app.utils.logs.setup.get_shared_queue_handler"
    assert cfg["filters"]["uvicorn_app"]["appname"] == "uvicorn"
    # 공유 핸들러를 오염시키면 안 되므로 핸들러에는 필터를 두지 않는다.
    assert "filters" not in cfg["handlers"]["queue"]


def test_shared_queue_handler_is_the_app_queue_handler():
    """uvicorn 이 받는 핸들러가 앱이 쓰는 바로 그 인스턴스여야 한다.

    두 개가 되면 queue 도 listener 도 둘이 되어 출력 순서와 종료 시점이 갈린다.
    (root 로거 자체는 pytest 의 로그 캡처가 가로채므로 여기서 단언하지 않는다 —
    root 배선은 ``test_root_uses_queue_handler_only`` 가 dictConfig 로 검증한다.)
    """
    from app.utils.logs.queue_handler import BoundedQueueHandler
    from app.utils.logs.setup import get_queue_handler, get_shared_queue_handler

    handler = get_queue_handler()
    assert isinstance(handler, BoundedQueueHandler)
    assert get_shared_queue_handler() is handler


def test_configure_logging_applies_once(monkeypatch):
    """configure_logging() 은 여러 번 불러도 dictConfig 를 1회만 적용한다.

    get_logger() 가 매번 호출하므로, 여기서 idempotent 가 깨지면 로거를 만들 때마다
    전체 로깅이 재구성되어 런타임에 붙인 핸들러가 사라진다.
    """
    calls = []
    monkeypatch.setattr(logs_setup, "dictConfig", lambda cfg: calls.append(cfg))
    monkeypatch.setattr(logs_setup, "_configured", False, raising=False)

    logs_setup.configure_logging()
    logs_setup.configure_logging()
    get_logger("test.idempotent")
    assert len(calls) == 1

    # force=True 는 의도적 재적용이므로 통과해야 한다.
    logs_setup.configure_logging(force=True)
    assert len(calls) == 2


# =============================================================================
# 프로세스 수명 listener (ADR-018 / F-029)
#
# listener 의 소유자는 FastAPI lifespan 이 아니라 프로세스다. lifespan 이 멈추면
# 그 뒤에 나오는 uvicorn 최종 로그와 startup 실패 traceback 이 큐에 갇혀 사라진다.
# =============================================================================
def test_process_exit_hook_is_registered_once(monkeypatch):
    """로깅 구성 시 프로세스당 **한 번만** 종료 훅을 등록한다 (ADR-018).

    여러 번 등록되면 종료 때 stop 이 여러 번 불리고, 등록이 아예 없으면 프로세스가
    listener 를 남긴 채 죽는다. 실제 스레드를 만들지 않도록 dictConfig 와 listener
    전역을 막아 두고 등록 횟수만 본다.
    """
    registered: list = []
    monkeypatch.setattr(logs_setup.atexit, "register", lambda fn: registered.append(fn))
    monkeypatch.setattr(logs_setup, "_exit_hook_registered", False, raising=False)
    monkeypatch.setattr(logs_setup, "dictConfig", lambda cfg: None)
    monkeypatch.setattr(logs_setup, "_configured", False)
    # 실제 listener 를 멈추지 않도록 — configure_logging 은 재구성 전에 stop 을 부른다.
    monkeypatch.setattr(logs_setup, "_listener", None)
    # 그리고 **새 listener 도 만들지 않도록** 막는다. queue 는 프로세스가 공유하므로
    # 여기서 두 번째 소비자가 생기면, 다음 stop 이 넣는 sentinel 을 원래 listener 가
    # 먼저 가져가고 이쪽 join() 이 영원히 대기한다(실제로 이 테스트가 멈췄다 — F-037).
    # `_queue_handler` 를 비우는 것으로는 막을 수 없다. configure_logging() 이 그 값을
    # 내부에서 다시 계산하기 때문이다. 생성 지점 자체를 갈아끼운다.
    monkeypatch.setattr(logs_setup, "start_log_listener", lambda: None)

    logs_setup.configure_logging()
    logs_setup.configure_logging(force=True)

    assert registered == [
        logs_setup.stop_log_listener
    ], f"프로세스 종료 훅 등록이 1회가 아니다: {registered}"


def test_stop_reports_lifecycle_outside_the_queue_and_is_idempotent(monkeypatch):
    """listener 종료 상태는 queue 를 거치지 않는 최종 sink 로 나가고, stop 은 멱등이다.

    종료 상태를 평소 logger 로 남기면 그 record 는 지금 멈추는 중인 listener 의
    queue 로 들어간다 — 자기 죽음을 자기가 보고하려다 아무 데도 못 남기는 구조다.
    F-026·F-029 가 같은 함정이었다.
    """
    buf = io.StringIO()
    monkeypatch.setattr(logs_setup.sys, "__stderr__", buf)

    class _FakeListener:
        def __init__(self) -> None:
            self.stopped = 0

        def stop(self) -> None:
            self.stopped += 1

    fake = _FakeListener()
    monkeypatch.setattr(logs_setup, "_listener", fake)

    logs_setup.stop_log_listener()
    logs_setup.stop_log_listener()  # 두 번째는 no-op 이어야 한다

    assert fake.stopped == 1, "stop 을 두 번 불러 listener 를 두 번 멈췄다"
    text = buf.getvalue()
    assert "stop 시작" in text and "stop 완료" in text, f"종료 상태가 최종 sink 에 없다: {text!r}"
    assert text.count("stop 완료") == 1, f"멱등이 아니다 — 완료가 여러 번 기록됐다: {text!r}"


# =============================================================================
# ADR-021 / F-030 / F-037 — queue listener 를 표준 확장 지점으로 다룬다
#
# stdlib 의 QueueListener 는 두 곳이 무방비다.
#   · enqueue_sentinel() 이 put_nowait 이라 bounded queue 가 포화면 종료가 실패한다.
#   · stop() 의 thread.join() 에 timeout 이 없어, sentinel 이 소비되지 않으면 영원히
#     기다린다. atexit 훅에 물려 있으면 그대로 프로세스 종료가 막힌다(F-037, 실측).
# 둘 다 stdlib 이 지정한 확장 지점(enqueue_sentinel 오버라이드)으로 닫는다.
# =============================================================================
def _isolated_listener(maxsize: int = 0):
    """프로세스 공용 queue 를 건드리지 않는 독립 listener.

    공용 queue 에 두 번째 소비자를 만들면 sentinel 을 서로 가로채 join 이 멈춘다
    (Wave 3 에서 실제로 테스트가 2분 멈췄다).
    """
    q: queue.Queue = queue.Queue(maxsize=maxsize)
    return q, logs_queue.TimeoutSentinelListener(q, logging.NullHandler())


def test_enqueue_sentinel_waits_for_a_slot_instead_of_failing_immediately(monkeypatch):
    """queue 가 잠깐 가득 차 있어도 종료 sentinel 을 넣을 수 있어야 한다 (F-030).

    기본 구현(``put_nowait``)이면 이 지점에서 ``queue.Full`` 로 죽고, 그 여파로
    listener 손잡이를 잃는다.
    """
    monkeypatch.setattr(logs_queue, "SENTINEL_ENQUEUE_TIMEOUT_SECONDS", 2.0)
    q, listener = _isolated_listener(maxsize=1)
    q.put("occupied")

    def free_slot() -> None:
        time.sleep(0.1)
        q.get()

    threading.Thread(target=free_slot, daemon=True).start()

    listener.enqueue_sentinel()

    assert q.get() is listener._sentinel, "sentinel 이 queue 에 들어가지 않았다"


def test_stop_is_bounded_when_the_sentinel_never_arrives(monkeypatch):
    """소비 스레드가 sentinel 을 못 받아도 stop 은 예산 안에 반환한다 (F-037).

    Wave 3 에서 실제로 관측한 상황이다 — 같은 queue 에 소비자가 둘이면 sentinel 을
    다른 쪽이 가져가고 이쪽 join 이 영원히 대기한다. atexit 훅은 daemon 스레드 정리보다
    **먼저** 돌기 때문에, 이 join 이 그대로 프로세스 종료를 막는다.
    """
    monkeypatch.setattr(logs_queue, "LISTENER_JOIN_TIMEOUT_SECONDS", 0.2)
    q, listener = _isolated_listener()
    listener.start()
    # sentinel 이 영영 도착하지 않는 상황을 만든다.
    monkeypatch.setattr(listener, "enqueue_sentinel", lambda: None)

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        listener.stop()
    elapsed = time.monotonic() - started

    assert elapsed < 3.0, f"stop 이 예산 안에 반환하지 않았다 ({elapsed:.1f}s)"

    # 뒷정리 — 진짜 sentinel 을 넣어 스레드를 끝낸다.
    q.put(listener._sentinel)
    listener._thread.join(timeout=3)


def test_stop_keeps_the_handle_when_stopping_fails(monkeypatch):
    """stop 이 실패하면 전역 참조를 **유지**한다 — 버리면 회수할 손잡이가 없다 (F-030)."""

    class _FailingListener:
        def stop(self) -> None:
            raise TimeoutError("멈추지 않는다(의도적)")

    failing = _FailingListener()
    monkeypatch.setattr(logs_setup, "_listener", failing)

    with pytest.raises(TimeoutError):
        logs_setup.stop_log_listener()

    assert (
        logs_setup._listener is failing
    ), "stop 실패인데 손잡이를 버렸다 — 스레드는 살아 있는데 재시도할 방법이 없다"


def test_dictconfig_declares_the_queue_listener_natively(monkeypatch, tmp_path):
    """queue/listener 구성을 손으로 하지 않고 dictConfig 에 맡긴다 (ADR-021).

    ``()`` 커스텀 팩토리를 쓰면 stdlib 의 QueueHandler 특수 처리 경로를 통째로
    우회하게 되고, 그 결과 listener 생성·대상 핸들러 연결을 전부 손으로 해야 한다.
    """
    cfg = _build_with(monkeypatch, tmp_path, env="development")
    queue_cfg = cfg["handlers"]["queue"]

    assert "()" not in queue_cfg, "커스텀 팩토리로 되돌아가면 네이티브 지원을 우회한다"
    assert queue_cfg["class"] == "app.utils.logs.queue_handler.BoundedQueueHandler"
    assert queue_cfg["listener"] == "app.utils.logs.queue_handler.TimeoutSentinelListener"
    assert queue_cfg["handlers"] == ["console"], "listener 가 위임받을 출력 핸들러"
    assert queue_cfg["respect_handler_level"] is True


def test_restart_revives_the_listener_after_its_thread_is_gone(monkeypatch):
    """fork 직후처럼 스레드가 사라진 프로세스에서 listener 를 다시 세운다.

    Celery prefork 자식이 이 경로를 탄다. listener 객체에는 **죽은 스레드 참조**가
    남아 있어, 그대로 ``start()`` 하면 stdlib 이 "Listener already started" 로 거절한다.
    이 테스트가 없어서 지금까지 이 경로는 검증된 적이 없다.
    """

    class _StubListener:
        def __init__(self) -> None:
            self._thread = object()  # fork 를 넘어온 죽은 참조
            self.starts = 0

        def start(self) -> None:
            if self._thread is not None:
                raise RuntimeError("Listener already started")
            self._thread = object()
            self.starts += 1

    stub = _StubListener()
    monkeypatch.setattr(logs_setup, "_queue_handler", types.SimpleNamespace(listener=stub))
    monkeypatch.setattr(logs_setup, "_listener", stub)

    logs_setup.restart_log_listener()

    assert stub.starts == 1, "fork 후 listener 를 다시 세우지 못했다"


# ── 신호 종료 경로 (F-038) ──────────────────────────────────────────────────
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

# uvicorn 이 정상 종료를 마친 뒤 하는 일을 그대로 재현하는 관찰 스크립트.
# `capture_signals()` 는 자기 핸들러를 걷어내고 **원래 핸들러를 복구한 뒤 잡았던 신호를
# 다시 올린다**(uvicorn/server.py). 복구된 핸들러가 SIG_DFL 이면 프로세스는 그 자리에서
# 끝나고 atexit 훅은 돌지 않는다.
SIGNAL_EXIT_PROBE = """
import signal, sys
from app.utils.logs import get_logger

get_logger("f038-probe").info("종료 직전 꼬리 로그")

SIG = signal.SIGBREAK if sys.platform == "win32" else signal.SIGTERM
original = signal.signal(SIG, lambda s, f: None)   # uvicorn 이 자기 핸들러를 설치
signal.signal(SIG, original)                       # finally: 원래 핸들러 복구
signal.raise_signal(SIG)                           # 잡았던 신호 재-raise
print("SURVIVED_THE_SIGNAL", flush=True)
"""


def test_signal_shutdown_still_drains_the_log_listener():
    """신호로 죽는 경로에서도 listener 가 flush 되고 멈춘다 (F-038 / ADR-022).

    ``docker stop``·k8s 의 SIGTERM 과 Windows 의 CTRL_BREAK 는 기본 핸들러가
    ``SIG_DFL`` 이라 **프로세스를 그 자리에서 끝낸다.** uvicorn 은 정상 종료를 마친 뒤
    그 신호를 다시 올리므로, ADR-018 의 ``atexit`` 훅이 실행되지 않고 queue 에 남은
    꼬리 로그가 통째로 사라졌다. listener 스레드는 daemon 이라 같이 죽는다.

    SIGINT 은 이 문제가 없다 — 기본 핸들러가 ``KeyboardInterrupt`` 를 올려 정상 종료
    경로를 타므로 atexit 이 실행된다. 그래서 SIGINT 은 **건드리지 않는다.**

    신호를 삼키지 않는다는 것도 함께 본다. 삼키면 ``docker stop`` 이 종료되지 않는
    컨테이너를 만나 결국 SIGKILL 로 끌려 죽는다.
    """
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = str(PROJECT_ROOT)
    # 자식 출력 인코딩을 UTF-8 로 못 박는다 — Windows 콘솔 코드페이지(cp949)로 쓰면
    # 아래 UTF-8 디코딩에서 한글이 대체문자가 되어 검증이 조용히 실패한다.
    child_env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", SIGNAL_EXIT_PROBE],
        cwd=PROJECT_ROOT,
        env=child_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    out = proc.stdout + proc.stderr

    assert "[log-lifecycle] stop 완료" in out, (
        "신호로 종료되는 경로에서 listener 가 flush·정지되지 않았다 — 큐에 남은 "
        f"종료 로그가 유실된다 (F-038). 출력:\n{out}"
    )
    assert "SURVIVED_THE_SIGNAL" not in out, (
        "신호를 삼켰다. 정리 후에는 원래 종료 동작으로 돌아가야 한다 — 삼키면 "
        f"docker stop 이 SIGKILL 까지 기다리게 된다. 출력:\n{out}"
    )
    assert proc.returncode != 0, "신호 종료인데 정상 종료 코드가 나왔다"


def test_wait_until_written_is_bounded_when_nothing_consumes():
    """소비자가 없으면 예산만큼만 기다리고 False 를 돌려준다 (ADR-023).

    ``Queue.join()`` 에는 timeout 이 없다. 그대로 썼다면 listener 가 죽어 있을 때
    종료가 영원히 매달렸을 것이다 — F-037 과 정확히 같은 함정이다.
    """
    log_queue: queue.Queue = queue.Queue()
    log_queue.put_nowait("소비되지 않을 record")

    started = time.monotonic()
    assert logs_queue.wait_until_written(log_queue, timeout=0.2) is False
    assert time.monotonic() - started < 5.0, "예산을 넘겨 기다렸다"


def test_wait_until_written_returns_true_once_the_consumer_finishes():
    """소비가 끝나면 곧바로 True 를 돌려준다.

    ``QueueListener._monitor`` 가 record 마다 ``task_done()`` 을 부르는 것을 그대로
    흉내낸다 — "unfinished_tasks 가 0" 이 곧 "넣은 걸 전부 썼다" 다.
    """
    log_queue: queue.Queue = queue.Queue()
    log_queue.put_nowait("record")

    def consume() -> None:
        log_queue.get_nowait()
        log_queue.task_done()

    threading.Timer(0.05, consume).start()

    assert logs_queue.wait_until_written(log_queue, timeout=5.0) is True


async def test_flush_is_a_no_op_when_no_listener_consumes(monkeypatch):
    """listener 가 없으면 기다리지 않는다 — 기다려 봐야 비지 않는다."""
    monkeypatch.setattr(logs_setup, "_listener", None)
    assert await logs_setup.flush_log_queue() is True
