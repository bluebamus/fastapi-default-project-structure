"""
UserAccessLog Pydantic 스키마

요청/응답 데이터 검증 및 직렬화를 위한 스키마입니다.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UserAccessLogBase(BaseModel):
    """UserAccessLog 기본 스키마"""

    ip_address: str = Field(..., description="IP 주소")
    request_path: str = Field(..., description="요청 경로")
    request_method: str = Field(..., description="HTTP 메서드")


class UserAccessLogCreate(UserAccessLogBase):
    """UserAccessLog 생성 스키마"""

    # 네트워크 정보
    forwarded_for: Optional[str] = Field(None, description="X-Forwarded-For 헤더")
    real_ip: Optional[str] = Field(None, description="X-Real-IP 헤더")

    # User-Agent 정보
    user_agent: Optional[str] = Field(None, description="User-Agent 문자열")
    os_name: Optional[str] = Field(None, description="운영체제 이름")
    os_version: Optional[str] = Field(None, description="운영체제 버전")
    browser_name: Optional[str] = Field(None, description="브라우저 이름")
    browser_version: Optional[str] = Field(None, description="브라우저 버전")

    # 장치 정보
    device_type: Optional[str] = Field(None, description="장치 유형 (desktop, mobile, tablet)")
    device_brand: Optional[str] = Field(None, description="장치 브랜드")
    device_model: Optional[str] = Field(None, description="장치 모델")
    is_bot: bool = Field(False, description="봇 여부")

    # 위치 정보
    country: Optional[str] = Field(None, description="국가")
    country_code: Optional[str] = Field(None, description="국가 코드")
    city: Optional[str] = Field(None, description="도시")

    # 요청 정보
    referer: Optional[str] = Field(None, description="Referer 헤더")
    query_string: Optional[str] = Field(None, description="쿼리 스트링")

    # 응답 정보
    response_status: Optional[int] = Field(None, description="응답 상태 코드")
    response_time_ms: Optional[int] = Field(None, description="응답 시간 (ms)")

    # 사용자 정보
    session_id: Optional[str] = Field(None, description="세션 ID")
    user_id: Optional[str] = Field(None, description="사용자 ID")

    # 추가 헤더
    accept_language: Optional[str] = Field(None, description="Accept-Language 헤더")


class UserAccessLogResponse(BaseModel):
    """UserAccessLog 응답 스키마"""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="로그 ID")
    ip_address: str = Field(..., description="IP 주소")
    os_name: Optional[str] = Field(None, description="운영체제 이름")
    os_version: Optional[str] = Field(None, description="운영체제 버전")
    browser_name: Optional[str] = Field(None, description="브라우저 이름")
    browser_version: Optional[str] = Field(None, description="브라우저 버전")
    device_type: Optional[str] = Field(None, description="장치 유형")
    device_brand: Optional[str] = Field(None, description="장치 브랜드")
    is_bot: bool = Field(..., description="봇 여부")
    country: Optional[str] = Field(None, description="국가")
    city: Optional[str] = Field(None, description="도시")
    request_path: str = Field(..., description="요청 경로")
    request_method: str = Field(..., description="HTTP 메서드")
    response_status: Optional[int] = Field(None, description="응답 상태 코드")
    response_time_ms: Optional[int] = Field(None, description="응답 시간 (ms)")
    user_id: Optional[str] = Field(None, description="사용자 ID")
    created_at: datetime = Field(..., description="생성 시간")


class UserAccessLogListResponse(BaseModel):
    """UserAccessLog 목록 응답 스키마"""

    items: list[UserAccessLogResponse] = Field(..., description="로그 목록")
    total: int = Field(..., description="전체 개수")
    skip: int = Field(..., description="건너뛴 개수")
    limit: int = Field(..., description="조회 개수")


class DeviceTypeStats(BaseModel):
    """장치 유형별 통계 스키마"""

    device_type: str = Field(..., description="장치 유형")
    count: int = Field(..., description="접속 수")


class OSStats(BaseModel):
    """OS별 통계 스키마"""

    os_name: str = Field(..., description="OS 이름")
    count: int = Field(..., description="접속 수")


class BrowserStats(BaseModel):
    """브라우저별 통계 스키마"""

    browser_name: str = Field(..., description="브라우저 이름")
    count: int = Field(..., description="접속 수")


class AccessLogStats(BaseModel):
    """접속 로그 통계 응답 스키마"""

    total_count: int = Field(..., description="전체 접속 수")
    device_types: list[DeviceTypeStats] = Field(..., description="장치 유형별 통계")
    os_list: list[OSStats] = Field(..., description="OS별 통계")
    browsers: list[BrowserStats] = Field(..., description="브라우저별 통계")
