"""CORSSettings 검증 규칙 테스트.

`allow_origins=["*"]` 와 `allow_credentials=True` 조합은 자격증명 포함 임의 출처 허용이라는
취약 설정이므로, 기동 시점(설정 검증)에 거부되어야 한다(fail-fast).
"""

import pytest
from pydantic import ValidationError

from config import CORSSettings


def test_wildcard_origin_with_credentials_is_rejected():
    """['*'] + credentials=True 조합은 ValidationError 로 거부된다."""
    with pytest.raises(ValidationError):
        CORSSettings(CORS_ALLOW_ORIGINS=["*"], CORS_ALLOW_CREDENTIALS=True)


def test_wildcard_origin_without_credentials_is_allowed():
    """['*'] + credentials=False 는 안전한 조합이므로 허용된다."""
    settings = CORSSettings(CORS_ALLOW_ORIGINS=["*"], CORS_ALLOW_CREDENTIALS=False)
    assert settings.CORS_ALLOW_ORIGINS == ["*"]
    assert settings.CORS_ALLOW_CREDENTIALS is False


def test_specific_origin_with_credentials_is_allowed():
    """구체 Origin + credentials=True 는 유효한 조합이므로 허용된다."""
    settings = CORSSettings(
        CORS_ALLOW_ORIGINS=["https://example.com"],
        CORS_ALLOW_CREDENTIALS=True,
    )
    assert settings.CORS_ALLOW_CREDENTIALS is True
