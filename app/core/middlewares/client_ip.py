"""클라이언트 IP 결정 — 신뢰하는 프록시 홉 수로만 판단한다 (service-hardening ADR-006·ADR-021).

``X-Forwarded-For`` 는 클라이언트가 마음대로 적을 수 있는 헤더다. 맨 왼쪽 값을 그대로
믿으면 헤더 한 줄로 접속 로그의 IP 가 위조된다. 믿을 수 있는 것은 **우리가 운영하는
프록시가 덧붙인 값**뿐이고, 프록시는 항상 목록의 오른쪽 끝에 붙인다. 그래서 운영
토폴로지를 "앞단 신뢰 프록시가 몇 홉인가" 하나로 표현한다(uvicorn
``--forwarded-allow-ips``·Werkzeug ``ProxyFix(x_for=N)`` 과 같은 모델).

- ``trusted_proxy_hops == 0``: 헤더를 보지 않는다. 직접 피어(``request.client.host``)가 답이다.
- ``trusted_proxy_hops == N``: ``X-Forwarded-For`` 목록의 **오른쪽에서 N번째** 값.
  직접 피어까지 이어 붙인 목록(``XFF + [peer]``)에서 피어를 0번째로 세면 N번째다.
  목록이 N개보다 짧으면 설정과 토폴로지가 어긋난 것이라 직접 피어를 쓴다.
- ``X-Real-IP`` 는 hops>0 이고 ``X-Forwarded-For`` 가 없을 때만 본다.
- 고른 값이 IP 주소가 아니면(포트가 붙었거나 쓰레기 값) 직접 피어로 물러난다.

배포 전 확인(설정 ``TRUSTED_PROXY_HOPS``): 프록시 뒤 배포면 앞단 프록시 단 수로 설정한다. 0 으로 두면
모든 클라이언트가 프록시 IP 하나로 보여 접속 로그와 로그인 레이트 리밋(API·관리 화면 모두 이 클래스를
쓴다)이 전체 사용자를 한 사람으로 취급하고, 실제보다 크게 잡으면 클라이언트가 적은 값을 믿게 돼 IP
위조가 가능하다.
"""

from __future__ import annotations

import ipaddress

from starlette.requests import Request

UNKNOWN_CLIENT = "unknown"


class ClientIPResolver:
    """요청 하나의 클라이언트 IP 를 정한다. 접속 로그 미들웨어가 생성자로 받는다."""

    def __init__(self, trusted_proxy_hops: int = 0) -> None:
        """
        Args:
            trusted_proxy_hops: 앱 앞단에서 ``X-Forwarded-For`` 를 덧붙이는 신뢰 프록시 수
        """
        if trusted_proxy_hops < 0:
            raise ValueError("trusted_proxy_hops 는 0 이상이어야 합니다.")
        self.trusted_proxy_hops = trusted_proxy_hops

    def resolve(self, request: Request) -> str:
        """클라이언트 IP 문자열(정규화된 표기). 피어도 없으면 ``"unknown"``."""
        peer = request.client.host if request.client else UNKNOWN_CLIENT
        if self.trusted_proxy_hops == 0:
            return peer

        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # 빈 항목도 자리로 센다 — 지우면 신뢰 경계가 왼쪽(클라이언트가 적은 값)으로 밀린다.
            hops = [hop.strip() for hop in forwarded_for.split(",")]
            if len(hops) < self.trusted_proxy_hops:
                return peer
            candidate = hops[-self.trusted_proxy_hops]
        else:
            candidate = (request.headers.get("X-Real-IP") or "").strip()

        return _normalized_ip(candidate) or peer


def _normalized_ip(value: str) -> str | None:
    """IP 주소면 정규화된 표기, 아니면 None."""
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None
