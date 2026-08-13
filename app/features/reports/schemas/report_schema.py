"""Reports 도메인 스키마 — Raw 집계 결과의 외부 계약 (Pydantic v2).

Raw 결과는 ORM 객체가 아니므로 ``from_attributes`` 에 의존하지 않는다.
``RowMapping`` 을 명시적으로 ``dict`` 로 바꿔 검증한다(RAW-REP-005).
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DailySalesItem(BaseModel):
    """하루치 매출 집계 한 줄."""

    sales_date: date = Field(description="매출 일자", examples=["2026-08-01"])
    order_count: int = Field(ge=0, description="주문 수", examples=[42])
    gross_amount: Decimal = Field(ge=0, description="총 매출", examples=["5120.50"])


class DailySalesReportResponse(BaseModel):
    """일별 매출 리포트 응답."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-07",
                    "items": [
                        {
                            "sales_date": "2026-08-01",
                            "order_count": 42,
                            "gross_amount": "5120.50",
                        }
                    ],
                }
            ]
        }
    )

    start_date: date = Field(description="조회 시작일(포함)")
    end_date: date = Field(description="조회 종료일(포함)")
    items: list[DailySalesItem] = Field(description="일자별 집계. 매출이 없는 날은 포함되지 않는다")
