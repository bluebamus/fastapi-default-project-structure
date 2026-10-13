"""Redis 서버 최소 버전 — log-redaction ADR-003.

최소 버전은 코드가 실제로 보내는 명령에서 정한다(``GETDEL`` → 6.2). lifespan 이 연결 직후
``INFO server`` 로 확인하고, 미만이면 기동을 멈춘다. ``INFO`` 를 막은 관리형 Redis·fakeredis 는
경고 후 계속한다.
"""

from __future__ import annotations

import ast
import logging
import pathlib

import pytest
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from redis.exceptions import ResponseError

from app.core import resources
from app.core.redis import REDIS_MIN_VERSION, RedisVersionError, ensure_redis_version

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app"


class _VersionedRedis:
    def __init__(self, version: str | None, *, info_error: Exception | None = None) -> None:
        self._version = version
        self._info_error = info_error
        self.closed = False

    async def ping(self) -> bool:
        return True

    async def info(self, section: str | None = None) -> dict:
        if self._info_error is not None:
            raise self._info_error
        return {} if self._version is None else {"redis_version": self._version}

    async def aclose(self) -> None:
        self.closed = True


def _patch_redis(monkeypatch, client: _VersionedRedis) -> None:
    class _Factory:
        @staticmethod
        def from_url(*args, **kwargs) -> _VersionedRedis:
            return client

    monkeypatch.setattr(resources, "Redis", _Factory)


@pytest.mark.parametrize("reported", ["6.0.16", "5.0.14", "4.0.9"])
async def test_startup_refuses_redis_below_the_minimum(monkeypatch, reported):
    client = _VersionedRedis(reported)
    _patch_redis(monkeypatch, client)
    app = FastAPI()

    with pytest.raises(RedisVersionError, match=reported):
        async with resources._redis(app):
            pytest.fail("최소 버전 미만인데 기동했다")

    assert app.state.redis is None
    assert client.closed, "기동을 멈출 때 연 클라이언트를 닫지 않았다"


@pytest.mark.parametrize("reported", ["6.2", "6.2.0", "7.0.15", "7.4.1", "8.0.2"])
async def test_startup_accepts_redis_at_or_above_the_minimum(monkeypatch, reported):
    client = _VersionedRedis(reported)
    _patch_redis(monkeypatch, client)
    app = FastAPI()

    async with resources._redis(app):
        assert app.state.redis is client


@pytest.mark.parametrize(
    "client",
    [
        _VersionedRedis(None, info_error=ResponseError("unknown command 'info'")),
        _VersionedRedis(None),  # redis_version 키가 없다
        _VersionedRedis("unknown"),
    ],
    ids=["info-blocked", "no-version-key", "unparseable"],
)
async def test_unverifiable_version_warns_and_continues(monkeypatch, caplog, client):
    _patch_redis(monkeypatch, client)
    app = FastAPI()

    with caplog.at_level(logging.WARNING, logger="redis"):
        async with resources._redis(app):
            assert app.state.redis is client

    assert any("버전을 확인하지 못했다" in r.getMessage() for r in caplog.records)


async def test_fakeredis_used_by_tests_does_not_block_startup():
    """테스트가 쓰는 fakeredis 는 ``INFO`` 를 모른다 — 경고 경로를 타고 통과해야 한다."""
    await ensure_redis_version(FakeAsyncRedis())


# =============================================================================
# 계약 — 상수가 코드에서 실제로 쓰는 명령의 요구 버전 이상인가
# =============================================================================
def _redis_calls() -> list[tuple[str, set[str], str]]:
    """``app/`` 의 메서드 호출 (이름, 키워드 집합, 위치)."""
    calls = []
    for path in APP_DIR.rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                keywords = {kw.arg for kw in node.keywords if kw.arg}
                where = f"{path.relative_to(APP_DIR.parent)}:{node.lineno}"
                calls.append((node.func.attr, keywords, where))
    return calls


def _required_version(name: str, keywords: set[str]) -> tuple[int, int, int] | None:
    if name in {"expire", "pexpire", "expireat", "pexpireat"} and keywords & {
        "nx",
        "xx",
        "gt",
        "lt",
    }:
        return (7, 0, 0)
    if name in {"getdel", "getex"}:
        return (6, 2, 0)
    if name == "set" and "nx" in keywords and keywords & {"ex", "px"}:
        return (2, 6, 12)
    return None


def test_min_version_covers_every_command_the_code_sends():
    needed = [
        (required, where, name)
        for name, keywords, where in _redis_calls()
        if (required := _required_version(name, keywords)) is not None
    ]
    assert any(
        name == "getdel" for _, _, name in needed
    ), "GETDEL 사용처를 찾지 못했다 — 검사가 죽었다"
    for required, where, name in needed:
        assert REDIS_MIN_VERSION >= required, (
            f"{where} 의 {name} 은 Redis {'.'.join(map(str, required))} 이상이 필요한데 "
            f"REDIS_MIN_VERSION 은 {REDIS_MIN_VERSION} 이다 — 상수와 문서를 함께 올린다"
        )


def test_min_version_is_not_inflated():
    """근거 없는 상향(예: 'Redis 7 필수')을 막는다 — 상수는 요구치 중 최댓값과 같아야 한다."""
    highest = max(
        required
        for name, keywords, _ in _redis_calls()
        if (required := _required_version(name, keywords)) is not None
    )
    assert REDIS_MIN_VERSION == highest
