"""Reports 기능 SQLAdmin 설정.

집계 결과가 아니라 **원본 주문 테이블**의 관리 화면이다. 주문 원장은 생성 후
변하지 않는 기록이므로 수정·삭제를 열지 않는다 — 관리 화면에서 과거 매출을
고칠 수 있으면 리포트를 신뢰할 수 없다.
"""

from sqladmin import ModelView

from app.features.reports.models.models import SalesOrder


class SalesOrderAdmin(ModelView, model=SalesOrder):
    """주문 원장 관리자 뷰(읽기 전용)."""

    name = "주문"
    name_plural = "주문"
    icon = "fa-solid fa-receipt"

    column_list = [
        SalesOrder.id,
        SalesOrder.customer,
        SalesOrder.total_amount,
        SalesOrder.created_at,
    ]
    column_default_sort = [(SalesOrder.created_at, True)]

    page_size = 50
    page_size_options = [25, 50, 100, 200]

    column_searchable_list = [SalesOrder.customer]
    column_filters = [SalesOrder.created_at]

    column_details_list = [
        SalesOrder.id,
        SalesOrder.customer,
        SalesOrder.total_amount,
        SalesOrder.created_at,
    ]

    # 생성 후 불변인 원장이다. 관리 화면에서 고칠 수 있으면 매출 리포트가 흔들린다.
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    can_export = True
    export_types = ["csv", "json"]

    column_labels = {
        SalesOrder.id: "ID",
        SalesOrder.customer: "고객",
        SalesOrder.total_amount: "주문 총액",
        SalesOrder.created_at: "주문 시각",
    }


admin_views: list[type] = [SalesOrderAdmin]
