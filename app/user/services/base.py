"""
기본 서비스 클래스

Repository 패턴을 사용하는 서비스의 기본 클래스입니다.
"""

from typing import Generic, TypeVar

from app.repositories.base import BaseRepository

R = TypeVar("R", bound=BaseRepository)


class BaseService(Generic[R]):
    """
    기본 서비스 클래스

    Repository를 주입받아 비즈니스 로직을 처리합니다.
    데이터 접근은 Repository에 위임합니다.

    Attributes:
        repository: 데이터 접근을 위한 Repository
    """

    def __init__(self, repository: R) -> None:
        """
        BaseService 초기화

        Args:
            repository: 데이터 접근을 위한 Repository
        """
        self.repository = repository
