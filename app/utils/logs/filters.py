"""로그 컨텍스트 필터.

record 에 두 필드를 주입한다.
- appname: 소스 파일 경로에서 앱 식별(domains/<app>, core, celery, utils, shared).
- classname:
    · 방식 C — LoggerAdapter/extra 로 이미 주입돼 있으면 그대로 존중(오버헤드 0).
    · 방식 A — 없으면 호출 프레임에서 self/cls 를 찾아 클래스명을 자동 추출.
  자유 함수(클래스 없음)는 '-'.
"""
from __future__ import annotations

import logging
import sys


def _app_from_path(pathname: str) -> str:
    p = pathname.replace("\\", "/")
    if "/domains/" in p:
        return p.split("/domains/", 1)[1].split("/", 1)[0]
    for seg in ("/app/core/", "/app/celery/", "/app/utils/", "/app/shared/"):
        if seg in p:
            return seg.strip("/").rsplit("/", 1)[-1]
    if "/app/" in p:
        return "app"
    return "ext"


def _class_from_stack() -> str:
    """호출 스택에서 logging/이 패키지 프레임을 건너뛰고 첫 사용자 프레임의 클래스명을 찾는다."""
    frame = sys._getframe(0)
    while frame is not None:
        filename = frame.f_code.co_filename.replace("\\", "/")
        if "/logging/" not in filename and "/utils/logs/" not in filename:
            local_self = frame.f_locals.get("self")
            if local_self is not None:
                return type(local_self).__name__
            local_cls = frame.f_locals.get("cls")
            if isinstance(local_cls, type):
                return local_cls.__name__
            return "-"
        frame = frame.f_back
    return "-"


class ContextFilter(logging.Filter):
    """record 에 appname/classname 을 채운다."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "appname", None):
            record.appname = _app_from_path(record.pathname)
        if not getattr(record, "classname", None):
            record.classname = _class_from_stack()
        return True
