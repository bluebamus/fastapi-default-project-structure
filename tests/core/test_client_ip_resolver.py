"""클라이언트 IP 결정 — service-hardening ADR-006·ADR-021 (F-006).

``X-Forwarded-For`` 는 클라이언트가 마음대로 적는다. 신뢰 프록시 홉 수(기본 0) 밖의
값은 믿지 않아야 헤더 한 줄로 접속 로그의 IP 를 위조할 수 없다.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core.middlewares.client_ip import ClientIPResolver
from config import MiddlewareSettings

PEER = "10.0.0.5"


def _request(headers: dict[str, str] | None = None, peer: str | None = PEER) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (peer, 1234) if peer else None,
    }
    return Request(scope)


def test_default_setting_trusts_no_proxy():
    """기본값은 0 — 설정하지 않은 배포가 헤더를 믿지 않는다."""
    assert MiddlewareSettings.model_fields["TRUSTED_PROXY_HOPS"].default == 0
    with pytest.raises(ValueError):
        MiddlewareSettings(TRUSTED_PROXY_HOPS=-1)


def test_zero_hops_ignores_forwarded_headers():
    request = _request({"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"})
    assert ClientIPResolver(0).resolve(request) == PEER


def test_one_hop_takes_the_rightmost_forwarded_value():
    """프록시 1단이 덧붙인 값(맨 오른쪽)만 믿는다 — 왼쪽은 클라이언트가 적은 값이다."""
    request = _request({"X-Forwarded-For": "6.6.6.6, 203.0.113.7"})
    assert ClientIPResolver(1).resolve(request) == "203.0.113.7"


def test_two_hops_take_the_second_from_the_right():
    request = _request({"X-Forwarded-For": "6.6.6.6, 203.0.113.7, 10.0.0.9"})
    assert ClientIPResolver(2).resolve(request) == "203.0.113.7"


def test_shorter_chain_than_hops_falls_back_to_peer():
    """설정보다 짧은 목록은 토폴로지와 어긋난 것 — 왼쪽 끝을 믿지 않는다."""
    request = _request({"X-Forwarded-For": "6.6.6.6"})
    assert ClientIPResolver(2).resolve(request) == PEER


@pytest.mark.parametrize("bogus", ["not-an-ip", "1.2.3.4:5678", "<script>", ""])
def test_invalid_value_falls_back_to_peer(bogus):
    request = _request({"X-Forwarded-For": f"6.6.6.6, {bogus}"})
    assert ClientIPResolver(1).resolve(request) == PEER


def test_ipv6_value_is_normalized():
    request = _request({"X-Forwarded-For": "2001:DB8:0:0::1"})
    assert ClientIPResolver(1).resolve(request) == "2001:db8::1"


def test_real_ip_is_used_only_without_forwarded_for():
    only_real_ip = _request({"X-Real-IP": "203.0.113.9"})
    assert ClientIPResolver(1).resolve(only_real_ip) == "203.0.113.9"

    both = _request({"X-Forwarded-For": "203.0.113.7", "X-Real-IP": "203.0.113.9"})
    assert ClientIPResolver(1).resolve(both) == "203.0.113.7"


def test_missing_peer_is_unknown():
    assert ClientIPResolver(0).resolve(_request(peer=None)) == "unknown"


def test_negative_hops_are_rejected():
    with pytest.raises(ValueError):
        ClientIPResolver(-1)
