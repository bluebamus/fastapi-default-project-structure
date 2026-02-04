"""
CORS (Cross-Origin Resource Sharing) 미들웨어

다른 도메인에서의 API 요청을 허용하기 위한 CORS 설정을 관리합니다.

CORS란?
    브라우저의 Same-Origin Policy로 인해 다른 도메인에서의 요청이 차단되는데,
    CORS 헤더를 통해 특정 도메인에서의 요청을 허용할 수 있습니다.

설정 위치:
    .env 파일 또는 config.py의 CORSSettings에서 설정합니다.

    CORS_ALLOW_ORIGINS=["http://localhost:3000", "https://example.com"]
    CORS_ALLOW_CREDENTIALS=true
    CORS_ALLOW_METHODS=["*"]
    CORS_ALLOW_HEADERS=["*"]

사용 예시:
    from app.core.middlewares.cors_middleware import CustomCORSMiddleware

    cors_middleware = CustomCORSMiddleware(app)
    cors_middleware.configure_cors()

주요 설정:
    - allow_origins: 허용할 도메인 목록 (["*"]은 모든 도메인 허용)
    - allow_credentials: 쿠키/인증 헤더 허용 여부
    - allow_methods: 허용할 HTTP 메서드 (GET, POST, PUT, DELETE 등)
    - allow_headers: 허용할 HTTP 헤더
    - expose_headers: 브라우저에 노출할 응답 헤더
    - max_age: Preflight 요청 캐시 시간 (초)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import cors_settings


class CustomCORSMiddleware:
    """
    CORS 미들웨어 설정 클래스

    FastAPI 애플리케이션에 CORS 설정을 적용합니다.
    설정값은 config.py의 CORSSettings에서 가져옵니다.

    Attributes:
        app: FastAPI 애플리케이션 인스턴스

    Example:
        app = FastAPI()
        cors = CustomCORSMiddleware(app)
        cors.configure_cors()
    """

    def __init__(self, app: FastAPI) -> None:
        """
        CustomCORSMiddleware 초기화

        Args:
            app: FastAPI 애플리케이션 인스턴스
        """
        self.app = app

    def configure_cors(self) -> None:
        """
        CORS 미들웨어를 애플리케이션에 추가합니다.

        CORSSettings의 설정값을 기반으로 CORS 정책을 구성합니다.

        Note:
            - 개발 환경: allow_origins=["*"]로 모든 도메인 허용
            - 운영 환경: 실제 프론트엔드 도메인만 허용 권장
            - allow_credentials=True일 때 allow_origins=["*"]는 보안상 권장하지 않음
        """
        self.app.add_middleware(
            CORSMiddleware,
            # 허용할 Origin 목록 (예: ["http://localhost:3000"])
            allow_origins=cors_settings.CORS_ALLOW_ORIGINS,
            # 쿠키, Authorization 헤더 등 인증 정보 허용
            allow_credentials=cors_settings.CORS_ALLOW_CREDENTIALS,
            # 허용할 HTTP 메서드 (["*"]는 모든 메서드)
            allow_methods=cors_settings.CORS_ALLOW_METHODS,
            # 허용할 요청 헤더
            allow_headers=cors_settings.CORS_ALLOW_HEADERS,
            # 브라우저에 노출할 응답 헤더
            expose_headers=cors_settings.CORS_EXPOSE_HEADERS,
            # Preflight 요청 캐시 시간 (초)
            max_age=cors_settings.CORS_MAX_AGE,
        )
