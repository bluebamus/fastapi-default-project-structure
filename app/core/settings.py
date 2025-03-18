""".env 환경설정 값을 관리합니다."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
from pydantic import field_validator

ENV_PATH = ".env"


class Settings(BaseSettings):
    """.env 파일 설정 모델"""

    # .env 파일을 읽어서 환경변수를 설정합니다.
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",  # extra=forbid (default)
        case_sensitive=True,
    )

    PROJECT_NAME: str = ""
    VERSION: str = ""
    DESCRIPTION: str = ""
    ENVIRONMENT: str = "development"

    DEBUG: bool = False  # 디버그 모드

    # 데이터베이스 설정
    DB_TABLE_PREFIX: str = ""
    DB_ENGINE: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_HOST: str = ""
    DB_PORT: int = 3306
    DB_NAME: str = ""
    DB_CHARSET: str = "utf8mb4"
    DATABASE_URL: str = "sqlite:///./test.db"

    SESSION_COOKIE_NAME: str = "session"  # 세션 쿠키 이름
    SESSION_SECRET_KEY: str = ""  # 세션 비밀키

    # SMTP 설정
    SMTP_SERVER: str = "localhost"
    SMTP_PORT: int = 25
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""

    TIME_ZONE: str = ""  # 시간대

    # 에디터 업로드 설정
    UPLOAD_IMAGE_RESIZE: bool = False  # 에디터 이미지 리사이즈 사용
    UPLOAD_IMAGE_SIZE_LIMIT: int = 20  # 이미지 업로드 제한 용량 (MB)
    UPLOAD_IMAGE_RESIZE_WIDTH: int = 1200  # 이미지 리사이즈 너비 (px)
    UPLOAD_IMAGE_RESIZE_HEIGHT: int = 2800  # 이미지 리사이즈 높이 (px)
    UPLOAD_IMAGE_QUALITY: int = 80  # 이미지 품질 (0~100)

    # CORS 설정
    CORS_ALLOW_ORIGINS: str = "*"
    CORS_ALLOW_CREDENTIALS: bool = False
    CORS_ALLOW_METHODS: str = "*"
    CORS_ALLOW_HEADERS: str = "*"
    CORS_EXPOSE_HEADERS: str = "*"
    CORS_MAX_AGE: int = 600

    # 유효성 검사 예시
    @field_validator("DATABASE_URL")
    def assemble_db_url(cls, v: Optional[str], values: dict) -> str:
        if v:
            return v
        return f"postgresql://{values.get('DB_USER')}:{values.get('DB_PASSWORD')}@{values.get('DB_HOST')}:{values.get('DB_PORT')}/{values.get('DB_NAME')}"


settings = Settings()
