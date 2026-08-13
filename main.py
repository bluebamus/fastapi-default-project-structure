"""FastAPI 진입점.

표준 FastAPI 구조: 각 기능 패키지가 취합한 ``router`` 를 여기서 ``include_router`` 로
최종 취합하고, 애플리케이션의 주요 설정(미들웨어·예외 핸들러·문서·lifespan·Admin)을 구성한다.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from scalar_fastapi import get_scalar_api_reference
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.db.session import READINESS_TIMEOUT_SECONDS, engine, ping_writer_db
from app.core.exception import AppException, ErrorResponse, ValidationException
from app.core.middlewares.cors_middleware import CustomCORSMiddleware
from app.core.middlewares.user_info_middleware import setup_user_info_middleware
from app.core.resources import manage_application_resources
from app.core.tags_metadata import tags_metadata
from app.features import auth, blog, home, reply, sns, user
from app.utils.logs import get_logger
from config import app_settings

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """애플리케이션 수명 주기 — 자원 관리자 호출만 담당한다 (AR-005).

    무엇을 어떤 순서로 만들고 해제하는지는 전부
    ``app/core/resources.py`` 의 ``manage_application_resources()`` 에 있다.
    자원별 코드를 여기 나열하면 종료 순서가 암묵적이 되고 startup 중간 실패에서
    이미 만든 자원이 새는 경로가 생긴다.
    """
    async with manage_application_resources(app):
        yield


def _register_exception_handlers(app: FastAPI) -> None:
    """4가지 글로벌 예외 핸들러를 등록합니다."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
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
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
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
        return JSONResponse(
            status_code=validation_exc.status_code,
            content=validation_exc.to_response().model_dump(mode="json"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
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
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error_code=f"HTTP_{exc.status_code}",
                message=str(exc.detail) if exc.detail else "HTTP 오류가 발생했습니다.",
                detail=None,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
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
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                message="내부 서버 오류가 발생했습니다.",
                detail=detail,
            ).model_dump(mode="json"),
        )


class HealthResponse(BaseModel):
    """헬스체크(liveness) 응답 스키마"""

    status: str = Field(description="프로세스 상태", examples=["healthy"])
    version: str = Field(description="애플리케이션 버전", examples=["0.1.0"])


class ReadyResponse(BaseModel):
    """준비 상태(readiness) 응답 스키마"""

    status: str = Field(description="준비 상태", examples=["ready"])


def _add_health_and_docs(app: FastAPI) -> None:
    """liveness·readiness 엔드포인트와 Scalar API 문서를 등록합니다."""

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="헬스체크(liveness)",
        description=(
            "프로세스가 살아 있는지만 확인합니다. **외부 연결을 검사하지 않습니다** — "
            "DB 가 잠깐 흔들릴 때 이 엔드포인트까지 실패하면 살아 있는 프로세스가 "
            "재시작됩니다. 의존 자원 준비 여부는 `/ready` 를 사용하세요."
        ),
        operation_id="healthCheck",
    )
    async def health_check() -> HealthResponse:
        """프로세스 생존 여부만 반환한다."""
        return HealthResponse(
            status="healthy",
            version=app_settings.VERSION,
        )

    @app.get(
        "/ready",
        response_model=ReadyResponse,
        tags=["Health"],
        summary="준비 상태(readiness)",
        description=(
            "트래픽을 받을 준비가 됐는지 확인합니다. writer DB 에 `SELECT 1` 을 "
            f"최대 {READINESS_TIMEOUT_SECONDS:.0f}초 안에 실행하고, 실패하거나 "
            "시간을 넘기면 503 을 반환합니다."
        ),
        operation_id="readinessCheck",
        responses={
            503: {
                "model": ErrorResponse,
                "description": "DB 를 사용할 수 없거나 응답이 늦어 준비되지 않음",
            }
        },
    )
    async def readiness_check() -> ReadyResponse:
        """writer DB 를 확인하고 준비 상태를 반환한다."""
        try:
            await ping_writer_db()
        except Exception as exc:
            # 상세는 서버 로그에만 남긴다. 헬스 엔드포인트는 보통 인증 없이 열려
            # 있어, 응답에 DSN·자격증명·드라이버 오류 원문이 실리면 그대로 유출된다.
            logger.warning(
                "[Readiness] DB 준비 확인 실패: %s",
                type(exc).__name__,
                extra={"exception_type": type(exc).__name__},
            )
            raise HTTPException(
                status_code=503,
                detail="서비스가 아직 요청을 받을 준비가 되지 않았습니다.",
            ) from exc
        return ReadyResponse(status="ready")

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
    # 응답 직렬화는 FastAPI 기본 경로(Pydantic 이 JSON 바이트를 직접 생성)를 쓴다.
    # 이전에는 default_response_class=ORJSONResponse 였으나, response_model 이 있으면
    # Pydantic 이 먼저 직렬화해 orjson 은 이미 문자열이 된 값만 보므로 이득이 없고
    # FastAPI 0.141 에서 deprecated 됐다. 제거 전후 응답 바이트가 동일함을 확인했다.
    docs_url=None,  # Swagger UI 비활성화 (Scalar 사용)
    redoc_url=None,  # ReDoc 비활성화 (Scalar 사용)
    openapi_url="/openapi.json" if app_settings.DEBUG else None,
)

# 미들웨어 설정
CustomCORSMiddleware(app).configure_cors()
setup_user_info_middleware(app)

# API 문서 상태 로깅
if app_settings.DEBUG:
    logger.info("API 문서 활성화 (DEBUG 모드): /docs, /openapi.json")
else:
    logger.info("API 문서 비활성화 (운영 모드): 보안을 위해 /docs, /openapi.json 접근 차단")

# 글로벌 예외 핸들러
_register_exception_handlers(app)
logger.info("글로벌 예외 핸들러 설정 완료")

# 라우터 취합 — 명시적 include_router (FastAPI 표준). 새 라우터는 여기에 한 줄 추가한다.
app.include_router(home.router, prefix="/api")
app.include_router(blog.router, prefix="/api")
app.include_router(reply.router, prefix="/api")
app.include_router(sns.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
logger.info("라우터 include 완료")

# 헬스체크 + Scalar 문서
_add_health_and_docs(app)

# SQLAdmin 관리자 페이지 (ADMIN 설정에 따라 활성화)
if app_settings.ADMIN:
    from app.features.admin import register_admin

    admin = register_admin(app, engine)
    logger.info("SQLAdmin 관리자 페이지 활성화 (ADMIN=True): /admin")
else:
    logger.info("SQLAdmin 관리자 페이지 비활성화 (ADMIN=False): /admin 접근 차단")


if __name__ == "__main__":
    import uvicorn

    from app.utils.logs import setup_uvicorn_logging

    uvicorn.run(
        "main:app",
        host=app_settings.SERVER_HOST,
        port=app_settings.SERVER_PORT,
        reload=app_settings.DEBUG,
        log_config=setup_uvicorn_logging(),
    )
