"""
Tests for HomeUnitOfWork declarative repository wiring.
"""

import pytest

from app.domains.home.unit_of_work import HomeUnitOfWork


@pytest.mark.asyncio
async def test_home_uow_has_repo():
    async with HomeUnitOfWork(background=True) as uow:
        assert uow.user_access_logs is not None
