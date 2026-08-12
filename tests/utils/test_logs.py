"""app/utils/logs 로깅 서브시스템 테스트.

검증: appname 산출, 클래스명 자동추출(A), 믹스인 주입(C), 포맷 필드, end-to-end.
"""

import io
import logging
import pathlib

from app.utils.logs import LOG_FORMAT, ContextFilter, LoggerMixin, TzFormatter, get_logger
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
