"""Catalog 도메인 스키마 — 상품 CRUD 요청/응답 모델 (Pydantic v2).

ORM 모델은 DB 매핑 계약이고, **Scalar 문서의 계약은 이 파일**이다(요구 §4.3).
컬럼 comment 는 DB 도구용이며 API 설명을 대체하지 않는다.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductBase(BaseModel):
    """상품 공통 필드."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="상품명",
        examples=["기계식 키보드"],
    )
    price: Decimal = Field(
        ...,
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="판매가(0보다 커야 함)",
        examples=["129.00"],
    )


class ProductCreate(ProductBase):
    """상품 생성 요청."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"name": "기계식 키보드", "price": "129.00", "is_active": True}]
        }
    )

    is_active: bool = Field(True, description="판매 활성 여부")


class ProductUpdate(BaseModel):
    """상품 수정 요청 — 전달된 필드만 부분 수정한다."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"price": "119.00"}]})

    name: str | None = Field(None, min_length=1, max_length=200, description="상품명")
    price: Decimal | None = Field(
        None,
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="판매가(0보다 커야 함)",
    )
    is_active: bool | None = Field(None, description="판매 활성 여부")


class ProductResponse(ProductBase):
    """상품 응답 — ORM 인스턴스에서 직접 변환한다."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="상품 UUID", examples=["3f1c1b8a-0f0e-4a3a-9a1e-0b2f5a7c1d90"])
    is_active: bool = Field(description="판매 활성 여부")
    created_at: datetime = Field(description="생성 시각")
    updated_at: datetime = Field(description="수정 시각")


class ProductListResponse(BaseModel):
    """상품 목록 응답(페이지네이션)."""

    items: list[ProductResponse] = Field(description="상품 목록")
    total: int = Field(ge=0, description="전체 상품 수")
    skip: int = Field(ge=0, description="건너뛴 수")
    limit: int = Field(ge=1, description="조회 제한 수")
