"""Catalog 기능 SQLAdmin 설정.

취합기 ``app/features/admin.py`` 가 이 모듈에서 직접 import 해 ADMIN_VIEWS 에 넣는다.
패키지 ``__init__.py`` 로 재노출하지 않는다 — 그러면 라우터만 필요한 import 에도
sqladmin 이 딸려 와 ADMIN=false 가 무의미해진다.
"""

from sqladmin import ModelView

from app.features.catalog.models.models import Product


class ProductAdmin(ModelView, model=Product):
    """상품 관리자 뷰."""

    name = "상품"
    name_plural = "상품"
    icon = "fa-solid fa-box"

    column_list = [
        Product.id,
        Product.name,
        Product.price,
        Product.is_active,
        Product.created_at,
    ]
    column_default_sort = [(Product.created_at, True)]

    page_size = 50
    page_size_options = [25, 50, 100, 200]

    column_searchable_list = [Product.name]
    column_filters = [Product.is_active, Product.created_at]

    column_details_list = [
        Product.id,
        Product.name,
        Product.price,
        Product.is_active,
        Product.created_at,
        Product.updated_at,
    ]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True
    export_types = ["csv", "json"]

    # id 는 UUID 기본값으로, 시각 컬럼은 모델의 default/onupdate 로 채워진다.
    form_excluded_columns = [Product.id, Product.created_at, Product.updated_at]

    column_labels = {
        Product.id: "ID",
        Product.name: "상품명",
        Product.price: "판매가",
        Product.is_active: "판매 활성",
        Product.created_at: "생성 시각",
        Product.updated_at: "수정 시각",
    }


admin_views: list[type] = [ProductAdmin]
