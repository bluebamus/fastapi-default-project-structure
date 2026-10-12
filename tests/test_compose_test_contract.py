"""테스트용 컨테이너는 loopback 에만 포트를 연다 (service-hardening ADR-024).

포트만 적으면 docker 는 0.0.0.0 에 연다. 인증 없는 테스트 Redis·MySQL 이 같은 네트워크의
다른 기기에 그대로 노출된다.
"""

from __future__ import annotations

import re
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[1] / "compose.test.yaml"

_PORT_LINE = re.compile(r'^\s*-\s*"([^"]+)"\s*$')


def _published_ports(text: str) -> list[str]:
    lines = text.splitlines()
    ports: list[str] = []
    in_ports = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped == "ports:":
            in_ports = True
            continue
        if in_ports:
            match = _PORT_LINE.match(line)
            if match:
                ports.append(match.group(1))
                continue
            in_ports = False
    return ports


def test_every_published_port_is_bound_to_loopback() -> None:
    ports = _published_ports(COMPOSE.read_text(encoding="utf-8"))
    assert len(ports) >= 2, ports  # mysql-test, redis-test
    exposed = [port for port in ports if not port.startswith("127.0.0.1:")]
    assert not exposed, f"loopback 이 아닌 포트 공개: {exposed}"
