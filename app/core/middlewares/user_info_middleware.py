"""
사용자 접속 정보 수집 미들웨어

모든 요청에서 사용자의 접속 정보를 수집하여 데이터베이스에 저장합니다.
"""

import time
from urllib.parse import urlencode

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp
from user_agents import parse as parse_user_agent

from app.core.middlewares.access_log_sink import get_access_log_sink
from app.core.middlewares.background_tasks import access_log_tasks
from app.core.middlewares.client_ip import ClientIPResolver
from app.utils.logs import get_logger
from config import middleware_settings, session_settings

logger = get_logger("user_info_middleware")

# 민감 쿼리 값 대신 저장하는 표식.
MASKED_VALUE = "***"


class UserInfoMiddleware(BaseHTTPMiddleware):
    """
    사용자 접속 정보 수집 미들웨어

    요청 시작 시 사용자 정보를 수집하고,
    응답 완료 후 백그라운드에서 데이터베이스에 저장합니다.

    수집 정보:
        - IP 주소 (신뢰 프록시 홉 수로만 헤더를 해석 — ClientIPResolver)
        - User-Agent 파싱 (OS, 브라우저, 장치 정보)
        - 요청 경로 및 메서드
        - 응답 상태 코드 및 시간
    """

    def __init__(self, app: ASGIApp, *, ip_resolver: ClientIPResolver) -> None:
        """
        미들웨어 초기화

        Args:
            app: 다음 ASGI 애플리케이션(add_middleware 가 주입)
            ip_resolver: 클라이언트 IP 결정기. ``setup_user_info_middleware`` 가 설정에서
                한 번 만들어 넘기고, 테스트는 다른 홉 수의 인스턴스를 넘긴다.
        """
        super().__init__(app)
        self.ip_resolver = ip_resolver
        self.enabled = middleware_settings.ACCESS_LOG_ENABLED
        self.exclude_paths = set(middleware_settings.ACCESS_LOG_EXCLUDE_PATHS)
        self.exclude_extensions = set(middleware_settings.ACCESS_LOG_EXCLUDE_EXTENSIONS)
        self.sensitive_query_keys = {
            key.lower() for key in middleware_settings.ACCESS_LOG_SENSITIVE_QUERY_KEYS
        }
        self.session_cookie_name = session_settings.SESSION_COOKIE_NAME

    def _should_skip(self, path: str) -> bool:
        """
        로깅을 건너뛸지 결정합니다.

        Args:
            path: 요청 경로

        Returns:
            건너뛸 경우 True
        """
        # 비활성화된 경우
        if not self.enabled:
            return True

        # 제외 경로인 경우
        if path in self.exclude_paths:
            return True

        # 제외 확장자인 경우
        for ext in self.exclude_extensions:
            if path.endswith(ext):
                return True

        return False

    def _masked_query_string(self, request: Request) -> str | None:
        """쿼리스트링을 민감 키의 값만 ``***`` 로 바꿔 다시 인코딩한다.

        토큰·비밀번호를 쿼리로 보내는 클라이언트가 있다 — 그대로 저장하면 접속 로그가
        비밀 저장소가 된다(service-hardening ADR-007). 키는 남겨 무엇이 왔는지는 보인다.
        """
        if not request.query_params:
            return None
        items = [
            (key, MASKED_VALUE if key.lower() in self.sensitive_query_keys else value)
            for key, value in request.query_params.multi_items()
        ]
        return urlencode(items, safe="*")

    def _parse_user_agent(self, user_agent_string: str | None) -> dict:
        """
        User-Agent 문자열을 파싱합니다.

        Args:
            user_agent_string: User-Agent 헤더 값

        Returns:
            파싱된 정보 딕셔너리
        """
        if not user_agent_string:
            return {
                "os_name": None,
                "os_version": None,
                "browser_name": None,
                "browser_version": None,
                "device_type": None,
                "device_brand": None,
                "device_model": None,
                "is_bot": False,
            }

        ua = parse_user_agent(user_agent_string)

        # 장치 유형 결정
        if ua.is_mobile:
            device_type = "mobile"
        elif ua.is_tablet:
            device_type = "tablet"
        elif ua.is_pc:
            device_type = "desktop"
        else:
            device_type = "other"

        return {
            "os_name": ua.os.family if ua.os.family != "Other" else None,
            "os_version": ua.os.version_string or None,
            "browser_name": ua.browser.family if ua.browser.family != "Other" else None,
            "browser_version": ua.browser.version_string or None,
            "device_type": device_type,
            "device_brand": ua.device.brand or None,
            "device_model": ua.device.model or None,
            "is_bot": ua.is_bot,
        }

    def _collect_request_info(self, request: Request) -> dict:
        """
        요청에서 정보를 수집합니다.

        Args:
            request: FastAPI Request 객체

        Returns:
            수집된 정보 딕셔너리
        """
        # User-Agent 파싱
        user_agent_string = request.headers.get("User-Agent")
        ua_info = self._parse_user_agent(user_agent_string)

        return {
            # 네트워크 정보 — 원본 헤더는 감사용으로 그대로 남기고, 판정은 resolver 가 한다.
            "ip_address": self.ip_resolver.resolve(request),
            "forwarded_for": request.headers.get("X-Forwarded-For"),
            "real_ip": request.headers.get("X-Real-IP"),
            # User-Agent 정보
            "user_agent": user_agent_string,
            **ua_info,
            # 요청 정보
            "request_path": request.url.path,
            "request_method": request.method,
            "query_string": self._masked_query_string(request),
            "referer": request.headers.get("Referer"),
            # 추가 헤더
            "accept_language": request.headers.get("Accept-Language"),
            # 사용자 정보. session_id 는 설정 SESSION_COOKIE_NAME 쿠키의 값이다. user_id 는
            # request.state.user_id 를 읽지만 현재 그 값을 설정하는 코드(인증 의존성 등)가
            # 없어 항상 None 이다.
            "session_id": request.cookies.get(self.session_cookie_name),
            "user_id": getattr(request.state, "user_id", None),
        }

    async def _save_access_log(self, data: dict) -> None:
        """
        접속 로그를 백그라운드에서 저장합니다.

        Args:
            data: 저장할 접속 로그 데이터
        """
        try:
            sink = get_access_log_sink()
            if sink is None:
                return
            await sink.save(data)
        except Exception as e:
            # 로그 저장 실패가 요청 처리에 영향을 주지 않도록 함.
            # 예외 메시지·트레이스백은 기본 로그에 남기지 않는다 — sink 는 DB 쓰기라
            # 예외의 str() 에 실행된 SQL 과 바인딩된 접속 정보가 들어 있다.
            logger.error("접속 로그 저장 실패: %s", type(e).__name__)
            logger.debug("접속 로그 저장 실패 상세", exc_info=True)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        미들웨어 메인 로직

        Args:
            request: FastAPI Request 객체
            call_next: 다음 미들웨어 또는 라우터 호출 함수

        Returns:
            Response 객체
        """
        path = request.url.path

        # 로깅 제외 대상인 경우 바로 다음으로 전달
        if self._should_skip(path):
            return await call_next(request)

        # 요청 시작 시간 기록
        start_time = time.perf_counter()

        logger.debug(f"[요청 시작] {request.method} {path}")

        # 요청 정보 수집
        request_info = self._collect_request_info(request)

        # 요청 처리. 처리되지 않은 예외는 바깥 ServerErrorMiddleware 가 500 으로 바꾸므로
        # 여기서는 예외로 보인다 — 500 으로 기록한 뒤 그대로 다시 던진다(ADR-007).
        try:
            response: Response = await call_next(request)
        except Exception:
            self._record(request_info, 500, start_time)
            raise

        self._record(request_info, response.status_code, start_time)
        return response

    def _record(self, request_info: dict, status_code: int, start_time: float) -> None:
        """응답 정보를 붙여 백그라운드 저장을 예약한다."""
        response_time_ms = int((time.perf_counter() - start_time) * 1000)
        request_info["response_status"] = status_code
        request_info["response_time_ms"] = response_time_ms

        logger.debug(
            f"[요청 완료] {request_info['request_method']} {request_info['request_path']} "
            f"- {status_code} ({response_time_ms}ms)"
        )

        # 백그라운드에서 로그 저장 (요청 처리를 블로킹하지 않음).
        # 상한 초과 시 드롭·집계되고, 앱 종료 시 lifespan 이 drain 한다(W1).
        access_log_tasks.spawn(self._save_access_log(request_info))


def setup_user_info_middleware(app: FastAPI) -> None:
    """
    UserInfoMiddleware를 FastAPI 앱에 등록합니다.

    Args:
        app: FastAPI 애플리케이션 인스턴스
    """
    # 결정기는 설정에서 한 번만 만든다 — 요청마다 설정을 다시 읽지 않는다.
    ip_resolver = ClientIPResolver(middleware_settings.TRUSTED_PROXY_HOPS)
    app.add_middleware(UserInfoMiddleware, ip_resolver=ip_resolver)
    logger.info("UserInfoMiddleware 등록 완료")
