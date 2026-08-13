"""상품 CRUD View (v1) — ORM workflow 참조 예제.

View 의 책임은 HTTP 계약, Service 호출, 응답 변환, 쓰기 성공 시 커밋뿐이다.
SQL 도 도메인 분기도 여기 두지 않는다.
"""

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.exception import ErrorResponse
from app.features.catalog.dependencies.catalog_dependencies import (
    get_catalog_service,
    get_catalog_service_readonly,
)
from app.features.catalog.schemas.catalog_schema import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)
from app.features.catalog.services.catalog_service import CatalogService

router = APIRouter()

_NOT_FOUND: dict = {
    404: {"model": ErrorResponse, "description": "상품을 찾을 수 없음"},
}
_CONFLICT: dict = {
    409: {"model": ErrorResponse, "description": "기존 데이터와 충돌"},
}


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_CONFLICT,
    summary="상품 생성",
    description="판매할 상품을 생성합니다. 생성 직후의 상품 정보를 반환합니다.",
    operation_id="createProduct",
)
async def create_product(
    payload: ProductCreate,
    service: CatalogService = Depends(get_catalog_service),
) -> ProductResponse:
    product = await service.create_product(payload)
    # 응답을 만들기 전에 정확히 한 번 커밋한다. 커밋이 실패하면 201 이 나가지 않는다.
    await service.commit()
    return ProductResponse.model_validate(product)


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="상품 목록 조회",
    description="상품을 페이지 단위로 조회합니다. `active_only=true` 면 판매 중인 상품만 반환합니다.",
    operation_id="listProducts",
)
async def list_products(
    skip: int = Query(0, ge=0, description="건너뛸 상품 수(offset)", examples=[0]),
    limit: int = Query(50, ge=1, le=100, description="조회할 상품 수(1-100)", examples=[50]),
    active_only: bool = Query(False, description="판매 중인 상품만 조회"),
    service: CatalogService = Depends(get_catalog_service_readonly),
) -> ProductListResponse:
    items, total = await service.list_products(skip=skip, limit=limit, active_only=active_only)
    return ProductListResponse(
        items=[ProductResponse.model_validate(item) for item in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    responses=_NOT_FOUND,
    summary="상품 단건 조회",
    description="ID로 상품을 조회합니다.",
    operation_id="getProduct",
)
async def get_product(
    product_id: str = Path(
        ...,
        description="상품 ID(UUID)",
        examples=["3f1c1b8a-0f0e-4a3a-9a1e-0b2f5a7c1d90"],
    ),
    service: CatalogService = Depends(get_catalog_service_readonly),
) -> ProductResponse:
    product = await service.get_product(product_id)
    return ProductResponse.model_validate(product)


@router.patch(
    "/products/{product_id}",
    response_model=ProductResponse,
    responses={**_NOT_FOUND, **_CONFLICT},
    summary="상품 수정",
    description="상품을 부분 수정합니다(전달한 필드만).",
    operation_id="updateProduct",
)
async def update_product(
    payload: ProductUpdate,
    product_id: str = Path(..., description="상품 ID(UUID)"),
    service: CatalogService = Depends(get_catalog_service),
) -> ProductResponse:
    product = await service.update_product(product_id, payload)
    await service.commit()
    return ProductResponse.model_validate(product)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    summary="상품 삭제",
    description="상품을 삭제합니다.",
    operation_id="deleteProduct",
)
async def delete_product(
    product_id: str = Path(..., description="상품 ID(UUID)"),
    service: CatalogService = Depends(get_catalog_service),
) -> None:
    await service.delete_product(product_id)
    await service.commit()
