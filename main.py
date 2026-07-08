"""FastAPI 진입점.

표준 FastAPI 구조: 각 도메인 앱 패키지가 취합한 ``router`` 를 여기서 ``include_router`` 로
최종 취합하고, 애플리케이션의 주요 설정(미들웨어·예외 핸들러·문서·lifespan·Admin)을 구성한다.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel
from scalar_fastapi import get_scalar_api_reference
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.db.session import create_db_tables, dispose_engine, engine
from app.core.exception import AppException, ErrorResponse, ValidationException
from app.core.middlewares.background_tasks import access_log_tasks
from app.core.middlewares.cors_middleware import CustomCORSMiddleware
from app.core.middlewares.user_info_middleware import setup_user_info_middleware
from app.core.rate_limit import limiter
from app.core.tags_metadata import tags_metadata
from app.domains import auth, blog, home, reply, sns, user
from app.utils.logs import get_logger
from config import app_settings

logger = get_logger("main")

# 최종 취합 대상 도메인 앱 (등록 순서 = 로드 순서). 새 앱은 여기에 추가한다.
APPS = [home, blog, reply, sns, user, auth]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    애플리케이션 수명 주기 관리

    시작 시:
        - DEBUG=True: 데이터베이스 테이블 자동 생성 (개발 환경용)
        - DEBUG=False: 테이블 생성 건너뜀 (운영 환경은 Alembic 사용)

    종료 시:
        - 데이터베이스 엔진 리소스 정리
    """
    logger.info("[Startup] 애플리케이션 시작 (DEBUG=%s)", app_settings.DEBUG)

    # DEBUG 모드일 때만 테이블 자동 생성
    # 운영 환경에서는 Alembic 마이그레이션 사용 권장
    if app_settings.DEBUG:
        try:
            await create_db_tables()
            logger.info("[Startup] 데이터베이스 테이블 생성 완료 (DEBUG 모드)")
        except Exception as e:
            logger.error("[Startup] 데이터베이스 테이블 생성 실패: %s", e)
            raise
    else:
        logger.info("[Startup] 테이블 자동 생성 건너뜀 (DEBUG=False, Alembic 사용)")

    yield

    logger.info("[Shutdown] 애플리케이션 종료 시작")
    # 엔진 정리 전에 진행 중인 백그라운드 로그 태스크를 drain (W1) —
    # dispose 와의 경합으로 인한 마지막 로그 유실을 줄인다.
    await access_log_tasks.drain()
    await dispose_engine()
    logger.info("[Shutdown] 애플리케이션 종료 완료")


def _register_exception_handlers(app: FastAPI) -> None:
    """4가지 글로벌 예외 핸들러를 등록합니다."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> ORJSONResponse:
        """
        애플리케이션 커스텀 예외 핸들러

        AppException 및 하위 예외들을 처리하여 일관된 에러 응답을 반환합니다.
        """
        logger.error(
            "[AppException] %s: %s",
            exc.error_code,
            exc.message,
            extra={
                "path": request.url.path,
                "method": request.method,
                "error_code": exc.error_code,
                "detail": exc.detail,
            },
        )
        return ORJSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> ORJSONResponse:
        """
        요청 유효성 검증 예외 핸들러

        Pydantic 유효성 검증 실패 시 일관된 에러 응답을 반환합니다.
        """
        errors = exc.errors()
        detail = [
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in errors
        ]
        logger.warning(
            "[ValidationError] 요청 유효성 검증 실패",
            extra={
                "path": request.url.path,
                "method": request.method,
                "errors": detail,
            },
        )
        validation_exc = ValidationException(
            message="요청 데이터 유효성 검증에 실패했습니다.",
            detail=detail,
        )
        return ORJSONResponse(
            status_code=validation_exc.status_code,
            content=validation_exc.to_response().model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> ORJSONResponse:
        """
        HTTP 예외 핸들러

        FastAPI/Starlette의 기본 HTTP 예외를 일관된 형식으로 변환합니다.
        """
        logger.warning(
            "[HTTPException] %s: %s",
            exc.status_code,
            exc.detail,
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code,
            },
        )
        return ORJSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error_code=f"HTTP_{exc.status_code}",
                message=str(exc.detail) if exc.detail else "HTTP 오류가 발생했습니다.",
                detail=None,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> ORJSONResponse:
        """
        일반 예외 핸들러

        처리되지 않은 모든 예외를 캐치하여 500 에러 응답을 반환합니다.
        운영 환경에서는 상세 정보를 숨깁니다.
        """
        logger.exception(
            "[UnhandledException] %s",
            type(exc).__name__,
            extra={
                "path": request.url.path,
                "method": request.method,
                "exception_type": type(exc).__name__,
            },
        )
        # DEBUG 모드에서만 상세 정보 노출 (운영 환경에서는 민감 정보 유출 방지)
        detail = str(exc) if app_settings.DEBUG else None
        return ORJSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                message="내부 서버 오류가 발생했습니다.",
                detail=detail,
            ).model_dump(),
        )


class HealthResponse(BaseModel):
    """헬스체크 응답 스키마"""

    status: str
    version: str


def _add_health_and_docs(app: FastAPI) -> None:
    """헬스체크 엔드포인트와 Scalar API 문서를 등록합니다."""

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="헬스체크",
        description="서버의 정상 동작 여부를 확인합니다.",
        operation_id="healthCheck",
    )
    async def health_check() -> HealthResponse:
        """
        헬스체크 엔드포인트

        Returns:
            서버 상태 정보
        """
        return HealthResponse(
            status="healthy",
            version=app_settings.VERSION,
        )

    # Scalar API 문서 (DEBUG 모드에서만 활성화)
    if app_settings.DEBUG:

        @app.get("/docs", include_in_schema=False)
        async def scalar_docs():
            """
            Scalar API 문서 페이지

            OpenAPI 스키마를 기반으로 인터랙티브 API 문서를 제공합니다.

            Note:
                이 엔드포인트는 DEBUG=True일 때만 활성화됩니다.
                운영 환경(DEBUG=False)에서는 보안을 위해 비활성화됩니다.
            """
            return get_scalar_api_reference(
                openapi_url=app.openapi_url,
                title=app_settings.PROJECT_NAME,
            )


# =============================================================================
# 애플리케이션 조립
# =============================================================================
app = FastAPI(
    title=app_settings.PROJECT_NAME,
    version=app_settings.VERSION,
    description=app_settings.DESCRIPTION,
    openapi_tags=tags_metadata,
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
    docs_url=None,  # Swagger UI 비활성화 (Scalar 사용)
    redoc_url=None,  # ReDoc 비활성화 (Scalar 사용)
    openapi_url="/openapi.json" if app_settings.DEBUG else None,
)

# 미들웨어 설정
CustomCORSMiddleware(app).configure_cors()
setup_user_info_middleware(app)

# 레이트 리밋 (slowapi) — 데코레이터 기반. 라우트에 @limiter.limit(...) 로 적용한다.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# API 문서 상태 로깅
if app_settings.DEBUG:
    logger.info("API 문서 활성화 (DEBUG 모드): /docs, /openapi.json")
else:
    logger.info("API 문서 비활성화 (운영 모드): 보안을 위해 /docs, /openapi.json 접근 차단")

# 글로벌 예외 핸들러
_register_exception_handlers(app)
logger.info("글로벌 예외 핸들러 설정 완료")

# 도메인 앱 라우터 최종 취합 (각 앱 패키지가 취합한 router 를 /api 에 마운트)
for _app in APPS:
    app.include_router(_app.router, prefix="/api")
logger.info("registered %d app routers", len(APPS))

# 헬스체크 + Scalar 문서
_add_health_and_docs(app)

# SQLAdmin 관리자 페이지 (ADMIN 설정에 따라 활성화)
if app_settings.ADMIN:
    from sqladmin import Admin

    admin = Admin(app, engine, title=f"{app_settings.PROJECT_NAME} Admin")
    for _app in APPS:
        for view in getattr(_app, "admin_views", []):
            admin.add_view(view)
    logger.info("SQLAdmin 관리자 페이지 활성화 (ADMIN=True): /admin")
else:
    logger.info("SQLAdmin 관리자 페이지 비활성화 (ADMIN=False): /admin 접근 차단")


if __name__ == "__main__":
    import uvicorn

    from app.utils.logs import setup_uvicorn_logging

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=app_settings.DEBUG,
        log_config=setup_uvicorn_logging(),
    )
