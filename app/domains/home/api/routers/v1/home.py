"""
Home v1 API 엔드포인트 — 접속 로그 조회/통계.

view 는 HTTP 역할만 한다: 파라미터 수신 → 의존성으로 주입된 Service 호출 → 응답 변환.
비즈니스 로직과 트랜잭션 경계는 services / dependencies 가 담당한다(UnitOfWork 제거).
"""

from fastapi import APIRouter, Depends, Path, Query

from app.core.exception import ErrorResponse
from app.domains.home.dependencies.access_log_dependencies import get_access_log_service
from app.domains.home.schemas.user_access_log_schema import (
    AccessLogStats,
    UserAccessLogListResponse,
    UserAccessLogResponse,
)
from app.domains.home.services.user_access_log_service import UserAccessLogService

router = APIRouter()

_ERR = {500: {"model": ErrorResponse, "description": "서버 내부 오류"}}


@router.get(
    "/access-logs",
    response_model=UserAccessLogListResponse,
    responses=_ERR,
    summary="접속 로그 목록 조회",
    description="접속 로그 목록을 페이지네이션하여 조회합니다.",
    operation_id="getAccessLogs",
)
async def get_access_logs(
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수(offset)"),
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    service: UserAccessLogService = Depends(get_access_log_service),
) -> UserAccessLogListResponse:
    logs, total = await service.get_access_logs(skip=skip, limit=limit)
    return UserAccessLogListResponse(
        items=[UserAccessLogResponse.model_validate(log) for log in logs],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/access-logs/recent",
    response_model=list[UserAccessLogResponse],
    responses=_ERR,
    summary="최근 접속 로그 조회",
    description="최근 접속 로그를 시간 역순으로 조회합니다.",
    operation_id="getRecentAccessLogs",
)
async def get_recent_access_logs(
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    service: UserAccessLogService = Depends(get_access_log_service),
) -> list[UserAccessLogResponse]:
    logs = await service.get_recent_logs(limit=limit)
    return [UserAccessLogResponse.model_validate(log) for log in logs]


@router.get(
    "/access-logs/by-ip/{ip_address}",
    response_model=list[UserAccessLogResponse],
    responses=_ERR,
    summary="IP별 접속 로그 조회",
    description="특정 IP 주소의 접속 로그를 조회합니다.",
    operation_id="getAccessLogsByIp",
)
async def get_access_logs_by_ip(
    ip_address: str = Path(..., description="조회할 IP 주소", example="192.168.1.1"),
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수"),
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    service: UserAccessLogService = Depends(get_access_log_service),
) -> list[UserAccessLogResponse]:
    logs = await service.get_logs_by_ip(ip_address=ip_address, skip=skip, limit=limit)
    return [UserAccessLogResponse.model_validate(log) for log in logs]


@router.get(
    "/access-logs/by-user/{user_id}",
    response_model=list[UserAccessLogResponse],
    responses=_ERR,
    summary="사용자별 접속 로그 조회",
    description="특정 사용자의 접속 로그를 조회합니다.",
    operation_id="getAccessLogsByUser",
)
async def get_access_logs_by_user(
    user_id: str = Path(..., description="조회할 사용자 ID(UUID)"),
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수"),
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    service: UserAccessLogService = Depends(get_access_log_service),
) -> list[UserAccessLogResponse]:
    logs = await service.get_logs_by_user(user_id=user_id, skip=skip, limit=limit)
    return [UserAccessLogResponse.model_validate(log) for log in logs]


@router.get(
    "/access-logs/stats",
    response_model=AccessLogStats,
    responses=_ERR,
    summary="접속 로그 통계",
    description="장치 유형/OS/브라우저별 접속 로그 통계를 조회합니다.",
    operation_id="getAccessLogStats",
)
async def get_access_log_stats(
    service: UserAccessLogService = Depends(get_access_log_service),
) -> AccessLogStats:
    return await service.get_stats()
