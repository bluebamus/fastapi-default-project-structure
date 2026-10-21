"""FastAPI 진입점.

표준 FastAPI 구조: 각 기능 패키지가 취합한 ``router`` 를 여기서 ``include_router`` 로
최종 취합하고, 애플리케이션의 주요 설정(미들웨어·예외 핸들러·문서·lifespan·Admin)을 구성한다.
"""

import asyncio
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from scalar_fastapi import get_scalar_api_reference
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.core.db.session import READINESS_TIMEOUT_SECONDS, engine, ping_writer_db
from app.core.exception import (
    AppException,
    ErrorResponse,
    ServiceUnavailableException,
    ValidationException,
)
from app.core.middlewares.cors_middleware import CustomCORSMiddleware
from app.core.middlewares.user_info_middleware import setup_user_info_middleware
from app.core.redis import get_redis
from app.core.resources import manage_application_resources
from app.core.security.access import AccessPolicyGuard, Public
from app.core.tags_metadata import tags_metadata
from app.features import auth, blog, catalog, home, reply, reports, sns, user
from app.utils.logs import get_logger
from app.utils.logs.filters import redact
from app.utils.logs.setup import attach_log_files
from config import app_settings

logger = get_logger("main")
# LOG_FILE_ENABLED 면 app.log·error.log (logging-overhaul L5). `python main.py`·`uvicorn` 은 설정 로드 직후
# 이미 붙었다(integration-e2e ADR-011) — 이 호출은 실행 프로그램으로 판정하지 못한 경우(`python -c`·테스트)용이다.
attach_log_files("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """애플리케이션 수명 주기 — 자원 관리자 호출만 담당한다 (AR-005).

    무엇을 어떤 순서로 만들고 해제하는지는 전부
    ``app/core/resources.py`` 의 ``manage_application_resources()`` 에 있다.
    자원별 코드를 여기 나열하면 종료 순서가 암묵적이 되고 startup 중간 실패에서
    이미 만든 자원이 새는 경로가 생긴다.
    """
    async with manage_application_resources(app):
        yield


def _with_bearer_challenge(
    status_code: int, headers: Mapping[str, str] | None
) -> dict[str, str] | None:
    """401 이면 ``WWW-Authenticate: Bearer`` 를 보탠다 — 로그인·refresh·logout·보호 라우트 전부 (integration-e2e ADR-013).

    RFC 9110 §15.5.2: 401 은 challenge 를 하나 이상 실어야 한다. 예외가 이미 실은 값은 그대로 둔다.
    """
    if status_code != 401:
        return dict(headers) if headers is not None else None
    return {"WWW-Authenticate": "Bearer", **(headers or {})}


def _register_exception_handlers(app: FastAPI) -> None:
    """글로벌 예외 핸들러(4가지 + Redis 연결 오류 503)를 등록합니다."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """
        애플리케이션 커스텀 예외 핸들러

        AppException 및 하위 예외들을 처리하여 일관된 에러 응답을 반환합니다.

        로그 레벨은 상태 코드로 정한다(service-hardening ADR-008 ④). 4xx 는 클라이언트
        입력이 원인이라 WARNING 이고 detail(요청 값이 들어 있을 수 있다)을 싣지 않는다 —
        ERROR 로 쌓으면 경보가 흐려진다. 5xx 만 ERROR 로 detail 과 함께 남긴다.
        """
        extra = {
            "path": request.url.path,
            "method": request.method,
            "error_code": exc.error_code,
            "status_code": exc.status_code,
        }
        if exc.status_code < 500:
            logger.warning("[AppException] %s: %s", exc.error_code, exc.message, extra=extra)
        else:
            logger.error(
                "[AppException] %s: %s",
                exc.error_code,
                exc.message,
                extra={**extra, "detail": exc.detail},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(mode="json"),
            headers=_with_bearer_challenge(exc.status_code, exc.headers),
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
            # 401 의 ``WWW-Authenticate: Bearer``(OAuth2PasswordBearer)처럼 예외가 실은 헤더를 보존한다.
            headers=_with_bearer_challenge(exc.status_code, exc.headers),
        )

    async def redis_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
        """Redis 연결 오류 → 503 ``SERVICE_UNAVAILABLE`` (integration-e2e ADR-009, F-004).

        레이트 리밋·refresh 회전·토큰 폐기는 Redis 가 없으면 진행할 수 없다 — fail-closed 로 요청을
        거부하되 일시 장애임을 503 으로 알린다(관리 화면의 Redis 장애 503 과 같은 의미). 아래
        ``Exception`` 핸들러로 떨어지면 Starlette ``ServerErrorMiddleware`` 가 응답 뒤 예외를 다시
        던져 uvicorn 이 traceback 을 한 번 더 남기고 keep-alive 연결을 닫는다 — 여기서 끝낸다.
        """
        logger.error(
            "[RedisUnavailable] %s",
            type(exc).__name__,
            exc_info=exc,
            extra={"path": request.url.path, "method": request.method},
        )
        unavailable = ServiceUnavailableException()
        return JSONResponse(
            status_code=unavailable.status_code,
            content=unavailable.to_response().model_dump(mode="json"),
        )

    # 연결 계열만 — 명령 오류(ResponseError 등)는 코드 결함이라 500 그대로 둔다.
    app.add_exception_handler(RedisConnectionError, redis_unavailable_handler)
    app.add_exception_handler(RedisTimeoutError, redis_unavailable_handler)

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
        # 응답은 클라이언트로 나간다 — 로그와 같은 규칙으로 비밀값을 가린다(log-redaction ADR-001).
        detail = redact(str(exc)) if app_settings.DEBUG else None
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                message="내부 서버 오류가 발생했습니다.",
                detail=detail,
            ).model_dump(mode="json"),
        )

    @app.middleware("http")
    async def unhandled_exception_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """처리기가 없는 예외를 ``ServerErrorMiddleware`` 바로 안쪽에서 받는다 (integration-e2e ADR-016).

        위 ``Exception`` 처리기만 두면 Starlette 가 그것을 ``ServerErrorMiddleware`` 에서 부르고 응답 뒤 예외를
        다시 던진다 — uvicorn 이 traceback 을 한 번 더 남기고 keep-alive 연결을 닫는다. 여기서 같은 처리기로
        응답을 끝내면 로그 1번·연결 유지·본문 그대로다. 사용자 미들웨어 중 **가장 바깥**이어야 CORS·UserInfo
        안에서 난 예외도 받는다 — 이 함수를 등록하는 이 호출이 미들웨어 등록의 마지막이다(테스트로 고정).
        ``DEBUG=true`` 는 지금처럼 다시 던진다. 응답 본문을 보내는 중의 예외는 ``call_next`` 가 이미 돌아온 뒤라
        여기 오지 않는다(기존대로 — 시작된 응답은 덧쓸 수 없다).
        """
        try:
            return await call_next(request)
        except Exception as exc:
            if app_settings.DEBUG:
                raise
            return await general_exception_handler(request, exc)


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
        dependencies=[Public],
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
            "트래픽을 받을 준비가 됐는지 확인합니다. writer DB 의 `SELECT 1` 과 Redis `PING` 을 "
            f"각각 최대 {READINESS_TIMEOUT_SECONDS:.0f}초 안에 동시에 실행하고, 하나라도 "
            "실패하거나 시간을 넘기면 503 을 반환합니다."
        ),
        operation_id="readinessCheck",
        dependencies=[Public],
        responses={
            503: {
                "model": ErrorResponse,
                "description": "DB 또는 Redis 를 사용할 수 없거나 응답이 늦어 준비되지 않음",
            }
        },
    )
    async def readiness_check(redis: Redis = Depends(get_redis)) -> ReadyResponse:
        """writer DB 와 Redis 를 동시에 확인하고 준비 상태를 반환한다 (ADR-011)."""

        async def ping_redis() -> None:
            async with asyncio.timeout(READINESS_TIMEOUT_SECONDS):
                await redis.ping()

        targets = ("DB", "Redis")
        results = await asyncio.gather(ping_writer_db(), ping_redis(), return_exceptions=True)
        failures = [
            (target, result)
            for target, result in zip(targets, results, strict=True)
            if isinstance(result, BaseException)
        ]
        for target, exc in failures:
            # 상세는 서버 로그에만, 그것도 대상과 예외 타입만 남긴다. 헬스 엔드포인트는 보통
            # 인증 없이 열려 있어, 응답이나 로그에 DSN·자격증명·드라이버 오류 원문이 실리면 새어 나간다.
            logger.warning(
                "[Readiness] %s 준비 확인 실패: %s",
                target,
                type(exc).__name__,
                extra={"readiness_target": target, "exception_type": type(exc).__name__},
            )
        if failures:
            raise HTTPException(
                status_code=503,
                detail="서비스가 아직 요청을 받을 준비가 되지 않았습니다.",
            )
        return ReadyResponse(status="ready")

    # Scalar API 문서 (DEBUG 모드에서만 활성화)
    if app_settings.DEBUG:

        @app.get("/docs", include_in_schema=False, dependencies=[Public])
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
# 데이터 접근 방식 참조 예제 — catalog 는 ORM, reports 는 Raw SQL.
app.include_router(catalog.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
logger.info("라우터 include 완료")

# 헬스체크 + Scalar 문서
_add_health_and_docs(app)


def _openapi_with_actual_422() -> dict:
    """422 문서를 실제 본문(``ErrorResponse``)으로 바꾼 OpenAPI (integration-e2e ADR-012).

    FastAPI 는 매개변수가 있는 operation 마다 422 를 기본 ``HTTPValidationError`` 로 광고하지만, 실제 응답은
    ``validation_exception_handler`` 가 만드는 ``ErrorResponse`` 다. 생성된 문서를 한 번 고쳐 캐시한다.
    """
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = FastAPI.openapi(app)
    schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    schemas.setdefault(
        "ErrorResponse",
        ErrorResponse.model_json_schema(ref_template="#/components/schemas/{model}"),
    )
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            documented = operation.get("responses", {}).get("422")
            if documented is not None:
                documented["content"] = {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                }
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)
    return schema


app.openapi = _openapi_with_actual_422  # type: ignore[method-assign]

# SQLAdmin 관리 화면 (ADMIN_DISABLED=true 면 끈다 — admin-login ADR-005).
# 끈 경우 sqladmin·인증 백엔드·세션 미들웨어를 import 하지도 만들지도 않고, 로그에도 경로를 싣지 않는다.
if not app_settings.ADMIN_DISABLED:
    from app.features.admin import register_admin

    # 슈퍼유저 로그인이 필요하다(admin-login ADR-001) — 계정은 scripts/create_superuser.py.
    admin = register_admin(app, engine)
    logger.info("SQLAdmin 관리 화면 활성화 (슈퍼유저 로그인 필요): /admin")
else:
    logger.info("관리 화면 비활성화 (ADMIN_DISABLED=true)")

# 기본 거부 — 조립이 끝난 앱의 모든 API 뷰가 접근 수준을 정확히 하나 선언했는지 검사하고,
# 아니면 위반 목록과 함께 기동을 멈춘다(access-policy ADR-003). 새 라우터 include 는 이 줄 위에 둔다.
AccessPolicyGuard().verify(app)


def run_server(target: str = "main:app") -> None:
    """개발용 서버 진입점 (ADR-020).

    ``log_config`` 은 uvicorn 이 문서화한 공식 파라미터다. 이걸로 넘겨야 uvicorn 3종
    로거가 앱과 **같은 queue·포맷**을 쓴다. 앱 쪽 ``build_dictconfig()`` 에 uvicorn
    로거를 심어 두는 방법도 동작하지만, 그건 *우리 설정이 uvicorn 것보다 나중에
    적용된다* 는 uvicorn 내부 순서에 기대는 것이라 이 파일만 봐서는 검증할 수 없다.

    ``uvicorn main:app`` CLI 로 띄워도 uvicorn 로그는 같은 포맷으로 나온다 — 앱 import 때
    ``configure_logging()`` 이 uvicorn 이 단 콘솔 핸들러를 공유 큐 핸들러로 바꾼다(logging-overhaul L1).
    오류·traceback 도 그대로 다 보인다(로그 유실은 listener 를 프로세스가 소유하게 한 ADR-018 에서
    해결했다). 두 경로의 차이는 SIGTERM 때 로그를 비우는 경로뿐이다.

    Args:
        target: 기동할 ASGI 앱의 import 문자열. Wave 7 의 subprocess 테스트가 정상
            앱과 startup 실패 앱을 **같은 경로로** 띄우기 위해 갈아끼운다.
    """
    import uvicorn

    from app.utils.logs import setup_uvicorn_logging

    uvicorn.run(
        target,
        host=app_settings.SERVER_HOST,
        port=app_settings.SERVER_PORT,
        reload=app_settings.DEBUG,
        log_config=setup_uvicorn_logging(),
    )


if __name__ == "__main__":
    run_server()
