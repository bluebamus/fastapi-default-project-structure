"""Core Repositories 패키지"""

from app.core.repositories.crud_base import CRUDBase
from app.core.repositories.repository_base import BaseRepository

__all__ = ["CRUDBase", "BaseRepository"]
