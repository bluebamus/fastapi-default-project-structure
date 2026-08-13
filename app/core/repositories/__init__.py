"""Core Repositories 패키지.

ORM 계층과 Raw SQL 계층은 **서로 상속하지 않는 평행 구조**다(AR-003)::

    BaseRepository     -> CRUDBase        (ORM 모델 반환)
    RawRepositoryBase  -> RawCRUDBase     (RowMapping/scalar/rowcount 반환)

공유하는 것은 ``AsyncSession`` 과 공통 예외·로깅 정책뿐이다.
"""

from app.core.repositories.crud_base import CRUDBase
from app.core.repositories.raw_crud_base import RawCRUDBase
from app.core.repositories.raw_repository_base import (
    RawRepositoryBase,
    resolve_identifier,
    resolve_sort_direction,
)
from app.core.repositories.repository_base import BaseRepository

__all__ = [
    "BaseRepository",
    "CRUDBase",
    "RawCRUDBase",
    "RawRepositoryBase",
    "resolve_identifier",
    "resolve_sort_direction",
]
