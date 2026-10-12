"""MySQL 8.4 에서 ORM 경로를 확인한다 (service-hardening ADR-009, ledger F-015).

MySQL 통합 테스트가 Raw SQL·migration 뿐이라, ORM 경로의 방언 차이(collation·strict
모드·길이 강제·정렬)는 SQLite 단위 테스트만 근거였다(검수 R-16). SQLite 는 길이를
강제하지 않고, 대소문자를 구분해 비교하며, NOT NULL 위반 메시지 형식도 다르다.
여기서는 실제 서비스·Repository 를 MySQL 세션으로 조립해 그 차이를 단언으로 고정한다.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.exception import DuplicateException, ValidationException
from app.features.catalog.exceptions import ProductNotFoundException
from app.features.catalog.models.models import Product
from app.features.catalog.repositories.product_repository import ProductRepository
from app.features.catalog.schemas.catalog_schema import ProductCreate, ProductUpdate
from app.features.catalog.services.catalog_service import CatalogService
from app.features.home.models.models import UserAccessLog
from app.features.home.services.user_access_log_service import UserAccessLogService
from app.features.user.repositories.user_repository import UserRepository

pytestmark = pytest.mark.mysql


async def test_catalog_crud_through_service(mysql_session_maker):
    """생성·조회·부분 수정·목록·삭제가 MySQL 에서 서비스 경로 그대로 동작한다."""
    async with mysql_session_maker() as db_session:
        service = CatalogService(db_session)
        created = await service.create_product(
            ProductCreate(name="기계식 키보드", price=Decimal("129.00"))
        )
        await service.commit()
        product_id = created.id

    async with mysql_session_maker() as db_session:
        service = CatalogService(db_session)
        fetched = await service.get_product(product_id)
        assert (fetched.name, fetched.price, fetched.is_active) == (
            "기계식 키보드",
            Decimal("129.00"),
            True,
        )

        updated = await service.update_product(product_id, ProductUpdate(price=Decimal("119.50")))
        await service.commit()
        assert updated.price == Decimal("119.50")
        assert updated.name == "기계식 키보드"  # 보내지 않은 필드는 유지

    async with mysql_session_maker() as db_session:
        service = CatalogService(db_session)
        items, total = await service.list_products()
        assert total == 1
        assert [(item.id, item.price) for item in items] == [(product_id, Decimal("119.50"))]

        await service.delete_product(product_id)
        await service.commit()

    async with mysql_session_maker() as db_session:
        with pytest.raises(ProductNotFoundException):
            await CatalogService(db_session).get_product(product_id)


async def test_same_created_at_is_ordered_by_id_and_pages_do_not_overlap(mysql_session_maker):
    """``created_at`` 동률은 PK 로 정렬되고 offset 페이지가 겹치거나 빠지지 않는다.

    MySQL 은 ORDER BY 가 정하지 않은 순서를 실행 계획에 맡긴다 — 동률 행의 순서가
    쿼리마다 달라지면 페이지가 겹치거나 행이 빠진다(ADR-005).
    """
    tied = datetime(2026, 10, 1, 12, 0, 0)
    newest = datetime(2026, 10, 1, 12, 0, 1)
    async with mysql_session_maker() as db_session:
        newest_product = Product(name="newest", price=Decimal("1.00"), created_at=newest)
        db_session.add(newest_product)
        for index in range(5):
            db_session.add(Product(name=f"tied-{index}", price=Decimal("1.00"), created_at=tied))
        await db_session.commit()
        newest_id = newest_product.id

    async with mysql_session_maker() as db_session:
        repository = ProductRepository(db_session)
        everything = [product.id for product in await repository.list(skip=0, limit=100)]
        pages = [
            [product.id for product in await repository.list(skip=skip, limit=2)]
            for skip in (0, 2, 4)
        ]

    assert len(everything) == 6
    assert everything[0] == newest_id
    assert everything[1:] == sorted(everything[1:], reverse=True)
    assert [product_id for page in pages for product_id in page] == everything


async def test_username_duplicate_is_case_insensitive(mysql_session_maker):
    """``utf8mb4_unicode_ci`` 에서 "Kim" 과 "kim" 은 같은 값이다 → 409.

    SQLite 는 대소문자를 구분해 두 행을 모두 받는다. 운영 동작은 collation 이 정하므로
    그 전제(compose.test.yaml 의 서버 collation)를 먼저 단언한다 — 전제가 바뀌면 이
    테스트가 무엇을 검증하는지부터 다시 정해야 한다.
    """
    async with mysql_session_maker() as db_session:
        collation = (
            await db_session.execute(
                text(
                    "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
                    "AND COLUMN_NAME = 'username'"
                )
            )
        ).scalar_one()
        assert collation == "utf8mb4_unicode_ci"

        repository = UserRepository(db_session)
        await repository.create({"username": "Kim", "email": "kim@example.com"})
        await db_session.commit()

        with pytest.raises(DuplicateException):
            await repository.create({"username": "kim", "email": "kim2@example.com"})
        await db_session.rollback()

    async with mysql_session_maker() as db_session:
        count = (await db_session.execute(text("SELECT COUNT(*) FROM users"))).scalar_one()
        assert count == 1


async def test_null_on_not_null_column_is_validation_error(mysql_session_maker):
    """strict 모드의 1048(Column cannot be null)은 422 로 변환된다(ADR-008 ②).

    스키마(``PatchSchema``)가 먼저 막지만, Repository 를 직접 쓰는 경로의 마지막 방어선은
    드라이버 코드 변환이다.
    """
    async with mysql_session_maker() as db_session:
        repository = ProductRepository(db_session)
        product = await repository.create({"name": "keep", "price": Decimal("1.00")})
        await db_session.commit()
        product_id = product.id  # rollback 이 인스턴스를 만료시키므로 미리 읽는다

        with pytest.raises(ValidationException):
            await repository.update_by_id(product_id, {"name": None})
        await db_session.rollback()

    async with mysql_session_maker() as db_session:
        stored = await ProductRepository(db_session).get_by_id(product_id)
        assert stored is not None
        assert stored.name == "keep"


async def test_long_access_log_values_are_stored_cut_to_column_length(mysql_session_maker):
    """길이 초과 값이 strict 모드 INSERT 를 실패시키지 않고 컬럼 길이로 잘려 저장된다(ADR-007)."""
    values = {
        "ip_address": "1.2.3.4",
        "request_method": "GET",
        "request_path": "/" + "p" * 5000,
        "forwarded_for": "6.6.6.6, " * 100,
        "session_id": "s" * 500,
        "user_agent": "u" * 2000,
        "referer": "https://example.com/" + "r" * 5000,
        "accept_language": "ko-KR," * 100,
        "query_string": "q=" + "v" * 300,
    }
    async with mysql_session_maker() as db_session:
        created = await UserAccessLogService(db_session).create_access_log(values)
        await db_session.commit()
        log_id = created.id

    async with mysql_session_maker() as db_session:
        stored = await db_session.get(UserAccessLog, log_id)
        assert stored is not None
        columns = UserAccessLog.__table__.c
        for name, value in values.items():
            length = getattr(columns[name].type, "length", None)
            expected = value if length is None else value[:length]
            assert getattr(stored, name) == expected, name
