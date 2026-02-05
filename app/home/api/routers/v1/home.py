"""
Home v1 API 엔드포인트

접속 로그 조회 및 통계 관련 엔드포인트를 제공합니다.

엔드포인트 목록:
    - GET /access-logs: 접속 로그 목록 조회 (페이지네이션)
    - GET /access-logs/recent: 최근 접속 로그 조회
    - GET /access-logs/by-ip/{ip_address}: IP별 접속 로그 조회
    - GET /access-logs/by-user/{user_id}: 사용자별 접속 로그 조회
    - GET /access-logs/stats: 접속 로그 통계 조회

사용 패턴:
    모든 엔드포인트는 다음 패턴을 따릅니다:
    1. session을 Depends로 주입받음
    2. HomeUnitOfWork 컨텍스트 내에서 Service 생성
    3. Repository가 HomeUnitOfWork에서 자동 주입됨
    4. Service 메서드 호출로 비즈니스 로직 실행
"""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exception import ErrorResponse
from app.database.session import get_session
from app.home.unit_of_work import HomeUnitOfWork
from app.home.schemas.user_access_log_schema import (
    UserAccessLogListResponse,
    UserAccessLogResponse,
    AccessLogStats,
)
from app.home.services.user_access_log_service import UserAccessLogService
from app.utils.logger import get_logger

logger = get_logger("home_router")

router = APIRouter()


# =============================================================================
# 접속 로그 목록 조회
# =============================================================================
@router.get(
    "/access-logs",
    response_model=UserAccessLogListResponse,
    responses={
        500: {"model": ErrorResponse, "description": "서버 내부 오류"},
    },
    summary="접속 로그 목록 조회",
    description="""
접속 로그 목록을 페이지네이션하여 조회합니다.

## 파라미터
- **skip**: 건너뛸 레코드 수 (기본값: 0)
- **limit**: 조회할 레코드 수 (기본값: 50, 최대: 100)

## 응답
- **items**: 접속 로그 목록
- **total**: 전체 레코드 수
- **skip**: 건너뛴 레코드 수
- **limit**: 조회 요청 수
    """,
    response_description="접속 로그 목록 및 페이지네이션 정보",
    operation_id="getAccessLogs",
)
async def get_access_logs(
    skip: int = Query(
        0,
        ge=0,
        description="건너뛸 레코드 수 (offset)",
        example=0,
    ),
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="조회할 레코드 수 (1-100)",
        example=50,
    ),
    session: AsyncSession = Depends(get_session),
) -> UserAccessLogListResponse:
    """
    접속 로그 목록을 조회합니다.

    Args:
        skip: 건너뛸 레코드 수
        limit: 조회할 레코드 수
        session: 데이터베이스 세션

    Returns:
        접속 로그 목록 및 페이지네이션 정보
    """
    logger.debug(f"[1/2] 접속 로그 목록 조회 요청: skip={skip}, limit={limit}")

    async with HomeUnitOfWork(session) as uow:
        service = UserAccessLogService(uow.user_access_logs)
        logs, total = await service.get_access_logs(skip=skip, limit=limit)

    logger.debug(f"[2/2] 접속 로그 목록 조회 완료: count={len(logs)}, total={total}")

    return UserAccessLogListResponse(
        items=[UserAccessLogResponse.model_validate(log) for log in logs],
        total=total,
        skip=skip,
        limit=limit,
    )


# =============================================================================
# 최근 접속 로그 조회
# =============================================================================
@router.get(
    "/access-logs/recent",
    response_model=list[UserAccessLogResponse],
    responses={
        500: {"model": ErrorResponse, "description": "서버 내부 오류"},
    },
    summary="최근 접속 로그 조회",
    description="""
최근 접속 로그를 시간 역순으로 조회합니다.

가장 최근 접속 기록부터 반환됩니다.
    """,
    response_description="최근 접속 로그 목록",
    operation_id="getRecentAccessLogs",
)
async def get_recent_access_logs(
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="조회할 레코드 수 (1-100)",
        example=50,
    ),
    session: AsyncSession = Depends(get_session),
) -> list[UserAccessLogResponse]:
    """
    최근 접속 로그를 조회합니다.

    Args:
        limit: 조회할 레코드 수
        session: 데이터베이스 세션

    Returns:
        최근 접속 로그 목록
    """
    logger.debug(f"[1/2] 최근 접속 로그 조회 요청: limit={limit}")

    async with HomeUnitOfWork(session) as uow:
        service = UserAccessLogService(uow.user_access_logs)
        logs = await service.get_recent_logs(limit=limit)

    logger.debug(f"[2/2] 최근 접속 로그 조회 완료: count={len(logs)}")

    return [UserAccessLogResponse.model_validate(log) for log in logs]


# =============================================================================
# IP별 접속 로그 조회
# =============================================================================
@router.get(
    "/access-logs/by-ip/{ip_address}",
    response_model=list[UserAccessLogResponse],
    responses={
        500: {"model": ErrorResponse, "description": "서버 내부 오류"},
    },
    summary="IP별 접속 로그 조회",
    description="""
특정 IP 주소의 접속 로그를 조회합니다.

## 사용 사례
- 특정 IP의 접속 이력 확인
- 의심스러운 IP 활동 모니터링
- 사용자 행동 패턴 분석
    """,
    response_description="해당 IP의 접속 로그 목록",
    operation_id="getAccessLogsByIp",
)
async def get_access_logs_by_ip(
    ip_address: str = Path(
        ...,
        description="조회할 IP 주소",
        example="192.168.1.1",
    ),
    skip: int = Query(
        0,
        ge=0,
        description="건너뛸 레코드 수",
        example=0,
    ),
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="조회할 레코드 수 (1-100)",
        example=50,
    ),
    session: AsyncSession = Depends(get_session),
) -> list[UserAccessLogResponse]:
    """
    IP 주소로 접속 로그를 조회합니다.

    Args:
        ip_address: IP 주소
        skip: 건너뛸 레코드 수
        limit: 조회할 레코드 수
        session: 데이터베이스 세션

    Returns:
        접속 로그 목록
    """
    logger.debug(f"[1/2] IP별 접속 로그 조회 요청: ip={ip_address}")

    async with HomeUnitOfWork(session) as uow:
        service = UserAccessLogService(uow.user_access_logs)
        logs = await service.get_logs_by_ip(
            ip_address=ip_address, skip=skip, limit=limit
        )

    logger.debug(f"[2/2] IP별 접속 로그 조회 완료: count={len(logs)}")

    return [UserAccessLogResponse.model_validate(log) for log in logs]


# =============================================================================
# 사용자별 접속 로그 조회
# =============================================================================
@router.get(
    "/access-logs/by-user/{user_id}",
    response_model=list[UserAccessLogResponse],
    responses={
        500: {"model": ErrorResponse, "description": "서버 내부 오류"},
    },
    summary="사용자별 접속 로그 조회",
    description="""
특정 사용자의 접속 로그를 조회합니다.

## 사용 사례
- 사용자의 접속 이력 확인
- 사용자 행동 분석
- 보안 감사 로그 확인
    """,
    response_description="해당 사용자의 접속 로그 목록",
    operation_id="getAccessLogsByUser",
)
async def get_access_logs_by_user(
    user_id: str = Path(
        ...,
        description="조회할 사용자 ID (UUID)",
        example="550e8400-e29b-41d4-a716-446655440000",
    ),
    skip: int = Query(
        0,
        ge=0,
        description="건너뛸 레코드 수",
        example=0,
    ),
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="조회할 레코드 수 (1-100)",
        example=50,
    ),
    session: AsyncSession = Depends(get_session),
) -> list[UserAccessLogResponse]:
    """
    사용자 ID로 접속 로그를 조회합니다.

    Args:
        user_id: 사용자 ID
        skip: 건너뛸 레코드 수
        limit: 조회할 레코드 수
        session: 데이터베이스 세션

    Returns:
        접속 로그 목록
    """
    logger.debug(f"[1/2] 사용자별 접속 로그 조회 요청: user_id={user_id}")

    async with HomeUnitOfWork(session) as uow:
        service = UserAccessLogService(uow.user_access_logs)
        logs = await service.get_logs_by_user(
            user_id=user_id, skip=skip, limit=limit
        )

    logger.debug(f"[2/2] 사용자별 접속 로그 조회 완료: count={len(logs)}")

    return [UserAccessLogResponse.model_validate(log) for log in logs]


# =============================================================================
# 접속 로그 통계
# =============================================================================
@router.get(
    "/access-logs/stats",
    response_model=AccessLogStats,
    responses={
        500: {"model": ErrorResponse, "description": "서버 내부 오류"},
    },
    summary="접속 로그 통계",
    description="""
접속 로그 통계를 조회합니다.

## 제공 통계
- **total_count**: 전체 접속 수
- **device_types**: 장치 유형별 통계 (desktop, mobile, tablet)
- **os_list**: 운영체제별 통계 (Windows, macOS, Linux, Android, iOS 등)
- **browsers**: 브라우저별 통계 (Chrome, Safari, Firefox 등)

## 사용 사례
- 대시보드 통계 표시
- 사용자 환경 분석
- 서비스 최적화 데이터 수집
    """,
    response_description="접속 로그 통계 정보",
    operation_id="getAccessLogStats",
)
async def get_access_log_stats(
    session: AsyncSession = Depends(get_session),
) -> AccessLogStats:
    """
    접속 로그 통계를 조회합니다.

    Args:
        session: 데이터베이스 세션

    Returns:
        접속 로그 통계 (장치 유형, OS, 브라우저별)
    """
    logger.debug("[1/2] 접속 로그 통계 조회 요청")

    async with HomeUnitOfWork(session) as uow:
        service = UserAccessLogService(uow.user_access_logs)
        stats = await service.get_stats()

    logger.debug("[2/2] 접속 로그 통계 조회 완료")

    return stats
