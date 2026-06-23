"""
Blog 도메인 전용 UnitOfWork (선언형 repositories 맵).

repositories 맵에 도메인 Repository를 선언하면 BaseUnitOfWork.__aenter__가
진입 시 자동으로 초기화한다. (아직 Repository가 없으므로 비어 있음)
"""

from app.core.db.unit_of_work import BaseUnitOfWork


class BlogUnitOfWork(BaseUnitOfWork):
    """Blog 도메인 전용 UnitOfWork."""

    repositories: dict[str, type] = {}
