"""클래스용 로거 믹스인 (방식 C).

클래스가 LoggerMixin 을 상속하면 self.log 로 클래스명이 주입된 로거를 쓸 수 있다.
LoggerAdapter 의 extra 로 classname 을 넣으므로 프레임 탐색(방식 A) 없이 오버헤드 0.
"""
from __future__ import annotations

import logging

from app.utils.logs.setup import get_logger


class LoggerMixin:
    """self.log 로 클래스명이 주입된 LoggerAdapter 를 제공한다."""

    @property
    def log(self) -> logging.LoggerAdapter:
        logger = get_logger(type(self).__module__)
        return logging.LoggerAdapter(logger, {"classname": type(self).__name__})
