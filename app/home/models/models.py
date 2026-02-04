"""
Home 모듈 데이터베이스 모델

접속자 정보를 저장하는 UserAccessLog 모델을 정의합니다.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, Integer, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from config import timezone_settings


class UserAccessLog(Base):
    """
    사용자 접속 정보 모델

    접속한 사용자의 OS, 장비, IP 등 상세 정보를 저장합니다.

    Attributes:
        id: UUID 기본키
        ip_address: 접속 IP 주소
        user_agent: 전체 User-Agent 문자열
        os_name: 운영체제 이름 (Windows, macOS, Linux 등)
        os_version: 운영체제 버전
        browser_name: 브라우저 이름 (Chrome, Firefox, Safari 등)
        browser_version: 브라우저 버전
        device_type: 장치 유형 (desktop, mobile, tablet)
        device_brand: 장치 브랜드 (Apple, Samsung 등)
        device_model: 장치 모델명
        is_bot: 봇/크롤러 여부
        country: 접속 국가
        country_code: 국가 코드
        city: 접속 도시
        referer: 유입 경로 (HTTP Referer)
        request_path: 요청 경로
        request_method: HTTP 메서드 (GET, POST 등)
        query_string: 쿼리 스트링
        response_status: 응답 상태 코드
        response_time_ms: 응답 시간 (밀리초)
        session_id: 세션 ID
        user_id: 로그인한 사용자 ID
        accept_language: Accept-Language 헤더
        created_at: 접속 시간
    """

    __tablename__ = "user_access_logs"

    # 테이블 인덱스 정의
    __table_args__ = (
        Index("ix_user_access_logs_created_at", "created_at"),
        Index("ix_user_access_logs_ip_address", "ip_address"),
        Index("ix_user_access_logs_os_name", "os_name"),
        Index("ix_user_access_logs_browser_name", "browser_name"),
        Index("ix_user_access_logs_device_type", "device_type"),
        Index("ix_user_access_logs_country", "country"),
        Index("ix_user_access_logs_session_id", "session_id"),
        Index("ix_user_access_logs_user_id", "user_id"),
    )

    # 기본키
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # 네트워크 정보
    ip_address: Mapped[str] = mapped_column(
        String(45),  # IPv6 지원
        nullable=False,
    )
    forwarded_for: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="X-Forwarded-For 헤더 값",
    )
    real_ip: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="X-Real-IP 헤더 값",
    )

    # User-Agent 정보
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    os_name: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    os_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    browser_name: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    browser_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    # 장치 정보
    device_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="desktop, mobile, tablet",
    )
    device_brand: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    device_model: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    is_bot: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # 위치 정보
    country: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    country_code: Mapped[Optional[str]] = mapped_column(
        String(3),
        nullable=True,
    )
    city: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # 요청 정보
    referer: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    request_path: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    request_method: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    query_string: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # 응답 정보
    response_status: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    response_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="응답 시간 (밀리초)",
    )

    # 사용자 정보
    session_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
    )

    # 추가 헤더 정보
    accept_language: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<UserAccessLog(id={self.id}, ip={self.ip_address}, "
            f"path={self.request_path}, created_at={self.created_at})>"
        )
