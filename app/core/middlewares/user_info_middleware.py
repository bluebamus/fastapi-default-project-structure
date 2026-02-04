"""
사용자 접속 정보 수집 미들웨어

모든 요청에서 사용자의 접속 정보를 수집하여 데이터베이스에 저장합니다.
"""

import asyncio
import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from user_agents import parse as parse_user_agent

from app.database.unit_of_work import BackgroundUnitOfWork
from app.home.services.user_access_log_service import UserAccessLogService
from app.utils.logger import get_logger
from config import middleware_settings

logger = get_logger("user_info_middleware")


class UserInfoMiddleware(BaseHTTPMiddleware):
    """
    사용자 접속 정보 수집 미들웨어

    요청 시작 시 사용자 정보를 수집하고,
    응답 완료 후 백그라운드에서 데이터베이스에 저장합니다.

    수집 정보:
        - IP 주소 (X-Forwarded-For, X-Real-IP 포함)
        - User-Agent 파싱 (OS, 브라우저, 장치 정보)
        - 요청 경로 및 메서드
        - 응답 상태 코드 및 시간
    """

    def __init__(self, app: FastAPI) -> None:
        """
        미들웨어 초기화

        Args:
            app: FastAPI 애플리케이션 인스턴스
        """
        super().__init__(app)
        self.enabled = middleware_settings.ACCESS_LOG_ENABLED
        self.exclude_paths = set(middleware_settings.ACCESS_LOG_EXCLUDE_PATHS)
        self.exclude_extensions = set(middleware_settings.ACCESS_LOG_EXCLUDE_EXTENSIONS)

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

    def _get_client_ip(self, request: Request) -> str:
        """
        클라이언트 IP 주소를 추출합니다.

        프록시 환경을 고려하여 X-Forwarded-For, X-Real-IP 헤더를 확인합니다.

        Args:
            request: FastAPI Request 객체

        Returns:
            클라이언트 IP 주소
        """
        # X-Forwarded-For 헤더 확인 (프록시/로드밸런서 환경)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # 첫 번째 IP가 실제 클라이언트 IP
            return forwarded_for.split(",")[0].strip()

        # X-Real-IP 헤더 확인
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 직접 연결된 클라이언트 IP
        if request.client:
            return request.client.host

        return "unknown"

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

        # 쿼리 스트링
        query_string = str(request.query_params) if request.query_params else None

        return {
            # 네트워크 정보
            "ip_address": self._get_client_ip(request),
            "forwarded_for": request.headers.get("X-Forwarded-For"),
            "real_ip": request.headers.get("X-Real-IP"),
            # User-Agent 정보
            "user_agent": user_agent_string,
            **ua_info,
            # 요청 정보
            "request_path": request.url.path,
            "request_method": request.method,
            "query_string": query_string,
            "referer": request.headers.get("Referer"),
            # 추가 헤더
            "accept_language": request.headers.get("Accept-Language"),
            # 사용자 정보 (인증 미들웨어에서 설정될 수 있음)
            "session_id": request.cookies.get("session_id"),
            "user_id": getattr(request.state, "user_id", None),
        }

    async def _save_access_log(self, data: dict) -> None:
        """
        접속 로그를 백그라운드에서 저장합니다.

        Args:
            data: 저장할 접속 로그 데이터
        """
        try:
            async with BackgroundUnitOfWork() as uow:
                # Repository를 주입받아 Service 생성
                service = UserAccessLogService(uow.user_access_logs)
                await service.create_access_log(data)
                await uow.commit()
        except Exception as e:
            # 로그 저장 실패가 요청 처리에 영향을 주지 않도록 함
            logger.error(f"접속 로그 저장 실패: {e}", exc_info=True)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
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

        # 요청 처리
        response: Response = await call_next(request)

        # 응답 시간 계산
        response_time_ms = int((time.perf_counter() - start_time) * 1000)

        # 응답 정보 추가
        request_info["response_status"] = response.status_code
        request_info["response_time_ms"] = response_time_ms

        logger.debug(
            f"[요청 완료] {request.method} {path} "
            f"- {response.status_code} ({response_time_ms}ms)"
        )

        # 백그라운드에서 로그 저장 (요청 처리를 블로킹하지 않음)
        asyncio.create_task(self._save_access_log(request_info))

        return response


def setup_user_info_middleware(app: FastAPI) -> None:
    """
    UserInfoMiddleware를 FastAPI 앱에 등록합니다.

    Args:
        app: FastAPI 애플리케이션 인스턴스
    """
    app.add_middleware(UserInfoMiddleware)
    logger.info("UserInfoMiddleware 등록 완료")
