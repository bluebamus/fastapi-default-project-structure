"""
Tests for declarative BaseUnitOfWork with repositories map and background flag.
"""

import pytest

from app.core.db.unit_of_work import BaseUnitOfWork


class _Repo:
    def __init__(self, session):
        self.session = session


class _UoW(BaseUnitOfWork):
    things: _Repo
    repositories = {"things": _Repo}


@pytest.mark.asyncio
async def test_repositories_autowired():
    async with _UoW() as uow:
        assert isinstance(uow.things, _Repo)
        assert uow.things.session is uow.session
