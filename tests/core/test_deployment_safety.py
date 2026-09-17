"""배포 안전 검사(`config.validate_deployment_safety`) 테스트 — ADR-027.

`ENV` 가 staging/production 이면 서명·세션 비밀 키가 예시 값(placeholder)이거나
access 와 refresh 키가 같을 때 config import 가 실패해야 한다. 오류 메시지는 설정
**이름**만 담고 값은 담지 않는다. development/test 는 검사하지 않는다.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import config

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
SECRET_KEYS = ("ACCESS_TOKEN_SECRET_KEY", "REFRESH_TOKEN_SECRET_KEY", "SESSION_SECRET_KEY")

STRONG = {
    "ACCESS_TOKEN_SECRET_KEY": "k9Qz0vL3mX7pR2tY5wB8nC1dF4gH6jK0aS3eU7iO9lZ",
    "REFRESH_TOKEN_SECRET_KEY": "Xr2Tq8Wm4Np6Lk0Jh3Gf5Ds7Az9Sx1Cv4Bn6Mm8Qw2Er",
    "SESSION_SECRET_KEY": "Pz7Ol5Ik3Uj1Yh9Tg7Rf5Ed3Ws1Qa8Zx6Cv4Bn2Mm0Lk",
}


def _example_secrets() -> dict[str, str]:
    """`.env.example` 에 적힌 세 비밀 키의 예시 값."""
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() in SECRET_KEYS:
            values[key.strip()] = value.strip()
    assert set(values) == set(SECRET_KEYS), ".env.example 에 비밀 키 예시가 모두 있어야 한다"
    return values


def _check(env: str, secrets: dict[str, str]) -> None:
    """.env·프로세스 환경과 무관하게 주어진 값만으로 검사를 실행한다."""
    config.validate_deployment_safety(
        app=config.AppSettings(_env_file=None, ENV=env),
        jwt=config.JWTSettings(
            _env_file=None,
            ACCESS_TOKEN_SECRET_KEY=secrets["ACCESS_TOKEN_SECRET_KEY"],
            REFRESH_TOKEN_SECRET_KEY=secrets["REFRESH_TOKEN_SECRET_KEY"],
        ),
        session=config.SessionSettings(
            _env_file=None, SESSION_SECRET_KEY=secrets["SESSION_SECRET_KEY"]
        ),
    )


@pytest.mark.parametrize("env", ["staging", "production"])
def test_env_example_secrets_are_rejected_without_leaking_values(env):
    """(a) `.env.example` 값 그대로면 거부되고, 메시지는 세 이름만 담는다."""
    secrets = _example_secrets()
    with pytest.raises(RuntimeError) as exc_info:
        _check(env, secrets)
    message = str(exc_info.value)
    for name in SECRET_KEYS:
        assert name in message
    for value in secrets.values():
        assert value not in message


def test_example_secrets_are_distinct():
    """예시 값 셋은 서로 달라야 한다(복사해 쓰다 같은 키가 되는 것을 막는다)."""
    assert len(set(_example_secrets().values())) == 3


@pytest.mark.parametrize("env", ["staging", "production"])
def test_distinct_strong_secrets_pass(env):
    """(b) 서로 다른 강한 키는 통과한다."""
    _check(env, STRONG)


def test_equal_access_and_refresh_are_rejected():
    """(c) access == refresh 는 거부되고, 메시지에 값이 없다."""
    secrets = {**STRONG, "REFRESH_TOKEN_SECRET_KEY": STRONG["ACCESS_TOKEN_SECRET_KEY"]}
    with pytest.raises(RuntimeError) as exc_info:
        _check("production", secrets)
    message = str(exc_info.value)
    assert "ACCESS_TOKEN_SECRET_KEY" in message
    assert "REFRESH_TOKEN_SECRET_KEY" in message
    assert STRONG["ACCESS_TOKEN_SECRET_KEY"] not in message


@pytest.mark.parametrize(
    "value",
    [
        "your-secret-key",
        "  YOUR-access-key  ",
        "change-this",
        "prod-CHANGE-THIS-please",
        "",
        "   ",
    ],
)
def test_placeholder_variants_are_rejected(value):
    """(d) `your-...`, `...change-this...`, 빈 값은 placeholder 다."""
    assert config.is_placeholder_secret(value)
    secrets = {**STRONG, "SESSION_SECRET_KEY": value}
    with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY"):
        _check("production", secrets)


@pytest.mark.parametrize("value", ["yours-truly-strong-key", "change_this_is_not_matched"])
def test_non_placeholder_values(value):
    """규칙에 걸리지 않는 값은 placeholder 가 아니다."""
    assert not config.is_placeholder_secret(value)


@pytest.mark.parametrize("env", ["development", "test"])
def test_development_and_test_are_not_checked(env):
    """(e) development/test 는 placeholder·동일 키여도 통과한다."""
    _check(env, _example_secrets())
    same = dict.fromkeys(SECRET_KEYS, "change-this")
    _check(env, same)


def _import_config(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **extra_env, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-c", "import config"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def test_import_fails_in_production_with_placeholders():
    """(f) 검사는 config import 시점에 실제로 돈다 — 비정상 종료, 값은 출력되지 않는다."""
    secrets = _example_secrets()
    result = _import_config({"ENV": "production", **secrets})
    assert result.returncode != 0
    assert "RuntimeError" in result.stderr
    for name in SECRET_KEYS:
        assert name in result.stderr
    for value in secrets.values():
        assert value not in result.stderr


def test_import_succeeds_in_production_with_strong_secrets():
    """(f) 같은 경로에서 강한 키면 import 가 성공한다."""
    result = _import_config({"ENV": "production", **STRONG})
    assert result.returncode == 0, result.stderr
