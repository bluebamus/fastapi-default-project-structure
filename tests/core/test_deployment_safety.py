"""설정 검사(`config.validate_deployment_safety` · `config.validate_env_source`) 테스트.

- ADR-027: 비밀 키가 예시 값(placeholder)이거나 access 와 refresh 키가 같으면 config import 가
  실패한다. 오류 메시지는 설정 **이름**만 담고 값은 담지 않는다.
- ADR-045 ①: `.env` 가 없고 필수 값이 환경 변수로도 없으면 실패한다(컨테이너 주입은 통과).
- ADR-045 ②: 위 비밀값 검사는 test 를 뺀 **모든 ENV** 에 적용된다(개발 환경 포함).
- admin-login ADR-004: ADR-045 ③(배포 환경의 켜진 관리 화면에 확인 플래그 요구)은 관리 화면 로그인이
  붙어 없앴다 — staging/production 에서 관리 화면을 켜도 통과하고, 예전 플래그가 남아 있어도 무시된다.
- admin-login ADR-005: 예전 설정 `ADMIN` 이 환경 변수·`.env` 에 남아 있으면 기동을 멈춘다(`ADMIN_DISABLED` 로 교체).
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


def _check(
    env: str,
    secrets: dict[str, str],
    *,
    debug: bool = False,
    log_level: str | None = "INFO",
    mysql_password: str = "Gt4Hn8Qz2Lp6Xw0Rb3Vy",
    redis_password: str | None = None,
    admin_disabled: bool = True,
) -> None:
    """.env·프로세스 환경과 무관하게 주어진 값만으로 검사를 실행한다."""
    config.validate_deployment_safety(
        app=config.AppSettings(
            _env_file=None,
            ENV=env,
            DEBUG=debug,
            ADMIN_DISABLED=admin_disabled,
        ),
        jwt=config.JWTSettings(
            _env_file=None,
            ACCESS_TOKEN_SECRET_KEY=secrets["ACCESS_TOKEN_SECRET_KEY"],
            REFRESH_TOKEN_SECRET_KEY=secrets["REFRESH_TOKEN_SECRET_KEY"],
        ),
        session=config.SessionSettings(
            _env_file=None, SESSION_SECRET_KEY=secrets["SESSION_SECRET_KEY"]
        ),
        log=config.LogSettings(_env_file=None, LOG_LEVEL=log_level),
        db=config.DatabaseSettings(_env_file=None, MYSQL_PASSWORD=mysql_password),
        redis=config.RedisSettings(_env_file=None, REDIS_PASSWORD=redis_password),
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


def test_test_env_is_not_checked():
    """(e) test 는 placeholder·동일 키여도 통과한다 — pytest 가 ENV=test 로 돈다."""
    _check("test", _example_secrets())
    same = dict.fromkeys(SECRET_KEYS, "change-this")
    _check("test", same, mysql_password="")


def test_development_rejects_example_secrets():
    """(e') ADR-045 ②: 개발 환경도 `.env.example` 값 그대로면 오류다 — `.env` 를 채우라는 신호."""
    secrets = _example_secrets()
    with pytest.raises(RuntimeError) as exc_info:
        _check("development", secrets)
    message = str(exc_info.value)
    for name in SECRET_KEYS:
        assert name in message
    for value in secrets.values():
        assert value not in message


@pytest.mark.parametrize("env", ["development", "staging", "production"])
def test_short_secret_key_is_rejected(env):
    """ADR-045 ②: 예시 값이 아니어도 32자보다 짧은 서명·세션 키는 거부한다."""
    short = "k9Qz0vL3mX7pR2tY5wB8nC1dF4g"  # 27자
    with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY") as exc_info:
        _check(env, {**STRONG, "SESSION_SECRET_KEY": short})
    assert short not in str(exc_info.value)


def _import_config(extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # DEBUG·LOG_LEVEL·비밀번호 2종은 배포 안전 검사 대상이다. 개발자 `.env` 값에
    # 좌우되지 않도록 기본을 고정하고, 해당 검사를 보는 테스트만 extra_env 로 덮어쓴다.
    # MYSQL_HOST·USER·DATABASE 는 `.env` 가 없는 환경(CI)에서 출처 검사(ADR-045 ①)를 통과시킨다.
    env = {
        **os.environ,
        "DEBUG": "false",
        "LOG_LEVEL": "INFO",
        "ADMIN_DISABLED": "true",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_USER": "app",
        "MYSQL_DATABASE": "app",
        "MYSQL_PASSWORD": "Gt4Hn8Qz2Lp6Xw0Rb3Vy",
        "REDIS_PASSWORD": "",
        **extra_env,
        "PYTHONIOENCODING": "utf-8",
    }
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


# ---------------------------------------------------------------------------
# debug 모드 거부 — 롤백 상세 로그가 debug 에서 SQL·바인딩 값을 남기므로,
# 배포 환경에서 debug 가 켜지지 못하게 같은 검사에서 막는다 (NFR-001).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("env", ["staging", "production"])
def test_debug_mode_is_rejected(env):
    """(g) `DEBUG=true` 는 배포 환경에서 거부되고, 메시지는 설정 이름만 담는다."""
    with pytest.raises(RuntimeError) as exc_info:
        _check(env, STRONG, debug=True)
    assert "DEBUG" in str(exc_info.value)


@pytest.mark.parametrize("value", ["DEBUG", "debug", "Debug"])
def test_debug_log_level_is_rejected(value):
    """(h) `LOG_LEVEL=DEBUG` 는 대소문자와 무관하게 거부된다."""
    with pytest.raises(RuntimeError) as exc_info:
        _check("production", STRONG, log_level=value)
    assert "LOG_LEVEL" in str(exc_info.value)


@pytest.mark.parametrize("log_level", [None, "INFO", "WARNING", "ERROR"])
def test_non_debug_log_levels_pass(log_level):
    """디버그가 아닌 레벨은 통과한다(미설정 포함 — DEBUG=false 면 INFO 로 풀린다)."""
    _check("production", STRONG, log_level=log_level)


@pytest.mark.parametrize("env", ["development", "test"])
def test_debug_mode_is_allowed_outside_deployed_envs(env):
    """개발·테스트에서는 debug 모드를 계속 쓴다."""
    _check(env, STRONG, debug=True, log_level="DEBUG")


def test_import_fails_in_production_with_debug_enabled():
    """(i) 검사는 import 시점에 실제로 돈다 — DEBUG=true 면 비정상 종료."""
    result = _import_config({"ENV": "production", **STRONG, "DEBUG": "true"})
    assert result.returncode != 0
    assert "RuntimeError" in result.stderr
    assert "DEBUG" in result.stderr


# ---------------------------------------------------------------------------
# 비밀번호 2종 — `.env.example` 값 그대로 배포 환경에 뜨는 것을 막는다.
#
# 빈 값 취급이 둘로 갈린다:
#   - `MYSQL_PASSWORD` 는 **비어 있으면 그 자체가 위반**이다. DB 는 이 스켈레톤이
#     반드시 붙는 대상이고, 빈 비밀번호는 인증 없는 접속을 뜻한다.
#   - `REDIS_PASSWORD` 는 **비어 있는 것이 정당한 구성**이다
#     (인증 없는 사설망 Redis). 값이 있을 때만 예시 값인지 본다.
# ---------------------------------------------------------------------------

PASSWORD_KEYS = ("MYSQL_PASSWORD", "REDIS_PASSWORD")


def _example_value(name: str) -> str:
    """`.env.example` 에 적힌 설정 값(없으면 빈 문자열)."""
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == name:
            return value.strip()
    raise AssertionError(f".env.example 에 {name} 이 없다")


@pytest.mark.parametrize("name", ["MYSQL_PASSWORD"])
def test_env_example_passwords_are_placeholders(name):
    """`.env.example` 의 비밀번호 예시는 검사에 걸리는 모양이어야 한다."""
    assert config.is_placeholder_secret(_example_value(name))


def test_env_example_redis_password_is_empty():
    """Redis 는 인증 없는 구성이 기본이라 예시를 비워 둔다(위반 아님)."""
    assert _example_value("REDIS_PASSWORD") == ""


@pytest.mark.parametrize("env", ["staging", "production"])
def test_example_mysql_password_is_rejected(env):
    """`.env.example` 의 MySQL 비밀번호 그대로면 거부되고, 값은 새지 않는다."""
    value = _example_value("MYSQL_PASSWORD")

    with pytest.raises(RuntimeError) as exc_info:
        _check(env, STRONG, mysql_password=value)

    assert "MYSQL_PASSWORD" in str(exc_info.value)
    assert value not in str(exc_info.value)


@pytest.mark.parametrize("env", ["staging", "production"])
def test_empty_mysql_password_is_rejected(env):
    """빈 MySQL 비밀번호 = 인증 없는 접속 — 배포 환경에서는 위반이다."""
    with pytest.raises(RuntimeError, match="MYSQL_PASSWORD"):
        _check(env, STRONG, mysql_password="")


@pytest.mark.parametrize("value", ["your-app-password", "change-this-redis-password"])
def test_placeholder_redis_password_is_rejected(value):
    """값을 넣었는데 예시 값이면 거부한다."""
    with pytest.raises(RuntimeError) as exc_info:
        _check("production", STRONG, redis_password=value)

    assert "REDIS_PASSWORD" in str(exc_info.value)
    assert value not in str(exc_info.value)


@pytest.mark.parametrize("env", ["staging", "production"])
def test_unused_redis_password_passes(env):
    """비어 있는 Redis 비밀번호는 "인증을 안 쓴다" 는 뜻이라 통과한다."""
    _check(env, STRONG, redis_password=None)
    _check(env, STRONG, redis_password="")
    _check(env, STRONG, redis_password="   ")


def test_passwords_are_not_checked_in_test_env():
    """테스트는 예시 비밀번호로 그냥 뜬다."""
    _check(
        "test",
        STRONG,
        mysql_password="",
        redis_password="your-redis-password",
    )


@pytest.mark.parametrize("mysql_password", ["", "EXAMPLE"])
def test_development_rejects_example_or_empty_mysql_password(mysql_password):
    """ADR-045 ②: 개발 환경도 MySQL 비밀번호가 비었거나 예시 값이면 오류다."""
    value = _example_value("MYSQL_PASSWORD") if mysql_password == "EXAMPLE" else ""
    with pytest.raises(RuntimeError, match="MYSQL_PASSWORD"):
        _check("development", STRONG, mysql_password=value)


def test_import_fails_in_production_with_example_passwords():
    """검사는 config import 시점에 실제로 돈다 — 값은 출력되지 않는다."""
    mysql_password = _example_value("MYSQL_PASSWORD")
    result = _import_config({"ENV": "production", **STRONG, "MYSQL_PASSWORD": mysql_password})

    assert result.returncode != 0
    assert "MYSQL_PASSWORD" in result.stderr
    assert mysql_password not in result.stderr


# ---------------------------------------------------------------------------
# admin-login ADR-004 — 관리 화면은 슈퍼유저 로그인이 필요하므로 배포 환경에서 켜 두어도 막지 않는다.
# 예전 확인 플래그(ADR-045 ③)는 설정·검사·기동 WARNING 에서 모두 빠졌다.
# admin-login ADR-005 — 예전 설정 `ADMIN` 이 남아 있으면 조용히 무시하지 않고 기동을 멈춘다.
# ---------------------------------------------------------------------------

LEGACY_ADMIN_FLAG = "ADMIN_ALLOW_UNAUTHENTICATED"


@pytest.mark.parametrize("env", ["development", "staging", "production", "test"])
def test_admin_enabled_passes_in_every_env(env):
    _check(env, STRONG, admin_disabled=False)


@pytest.mark.parametrize("name", ["ADMIN", "admin"])
@pytest.mark.parametrize("env", ["development", "staging", "production"])
def test_legacy_admin_env_var_stops_startup(tmp_path, env, name):
    with pytest.raises(RuntimeError) as exc_info:
        config.validate_no_legacy_admin(env, tmp_path / ".env", {name: "false"})
    assert "ADMIN_DISABLED" in str(exc_info.value)


def test_legacy_admin_in_env_file_stops_startup(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DEBUG=false\nADMIN=false\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="ADMIN_DISABLED"):
        config.validate_no_legacy_admin("production", env_file, {})


def test_new_admin_setting_does_not_trip_legacy_check(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_DISABLED=true\nADMIN_VIEWS=x\n", encoding="utf-8")
    config.validate_no_legacy_admin("production", env_file, {"ADMIN_DISABLED": "true"})


def test_legacy_admin_is_not_checked_under_test_env(tmp_path):
    config.validate_no_legacy_admin("test", tmp_path / ".env", {"ADMIN": "false"})


def test_import_fails_when_legacy_admin_is_set():
    """검사는 config import 시점에 실제로 돈다."""
    result = _import_config({"ENV": "production", **STRONG, "ADMIN": "false"})
    assert result.returncode != 0
    assert "ADMIN_DISABLED" in result.stderr


def test_legacy_admin_flag_is_gone_from_settings_and_code():
    assert LEGACY_ADMIN_FLAG not in config.AppSettings.model_fields
    for path in (
        PROJECT_ROOT / "config.py",
        PROJECT_ROOT / "main.py",
        PROJECT_ROOT / ".env.example",
        *(PROJECT_ROOT / "app").rglob("*.py"),
        *(PROJECT_ROOT / "scripts").rglob("*.py"),
    ):
        assert LEGACY_ADMIN_FLAG not in path.read_text(encoding="utf-8"), path


def test_leftover_legacy_admin_flag_in_env_file_is_ignored(tmp_path):
    """운영자의 `.env` 에 예전 줄이 남아 있어도 설정 로드가 깨지지 않는다(extra="ignore")."""
    env_file = tmp_path / ".env"
    env_file.write_text(f"{LEGACY_ADMIN_FLAG}=true\n", encoding="utf-8")
    settings = config.AppSettings(_env_file=env_file)
    assert settings.ADMIN_DISABLED is False


def test_deployed_admin_starts_without_flag_and_without_unauthenticated_warning():
    """production 에서 관리 화면을 켠 채(기본값) 앱이 뜬다. 예전 플래그가 환경에 남아 있어도 무시된다."""
    env = {
        **os.environ,
        "ENV": "production",
        **STRONG,
        "DEBUG": "false",
        "LOG_LEVEL": "INFO",
        "ADMIN_DISABLED": "false",
        LEGACY_ADMIN_FLAG: "true",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_USER": "app",
        "MYSQL_DATABASE": "app",
        "MYSQL_PASSWORD": "Gt4Hn8Qz2Lp6Xw0Rb3Vy",
        "REDIS_PASSWORD": "",
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    output = result.stdout + result.stderr
    assert "슈퍼유저 로그인 필요" in output
    assert "인증 없이" not in output


# ---------------------------------------------------------------------------
# ADR-045 ① — 설정의 출처. `.env` 가 없으면 필수 값이 환경 변수로 와야 한다.
# ---------------------------------------------------------------------------

FULL_ENVIRON = {
    "ENV": "production",
    **STRONG,
    "MYSQL_HOST": "db",
    "MYSQL_USER": "app",
    "MYSQL_PASSWORD": "Gt4Hn8Qz2Lp6Xw0Rb3Vy",
    "MYSQL_DATABASE": "app",
}


def test_missing_env_file_without_environ_is_rejected(tmp_path):
    with pytest.raises(RuntimeError) as exc_info:
        config.validate_env_source("development", tmp_path / ".env", {})
    message = str(exc_info.value)
    assert ".env" in message
    for name in config.REQUIRED_WITHOUT_ENV_FILE:
        assert name in message


def test_missing_env_file_names_only_what_is_missing(tmp_path):
    environ = {k: v for k, v in FULL_ENVIRON.items() if k != "MYSQL_PASSWORD"}
    with pytest.raises(RuntimeError) as exc_info:
        config.validate_env_source("production", tmp_path / ".env", environ)
    message = str(exc_info.value)
    assert "MYSQL_PASSWORD" in message
    assert "MYSQL_HOST" not in message
    for value in environ.values():
        assert value not in message


def test_injected_environ_without_env_file_passes(tmp_path):
    """컨테이너처럼 파일 없이 환경 변수로 모두 주입하면 통과한다."""
    config.validate_env_source("production", tmp_path / ".env", FULL_ENVIRON)


def test_existing_env_file_passes(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ENV=development\n", encoding="utf-8")
    config.validate_env_source("development", env_file, {})


def test_test_env_skips_source_check(tmp_path):
    config.validate_env_source("test", tmp_path / ".env", {})


def test_import_fails_without_env_file_and_environ(tmp_path):
    """검사는 import 시점에 실제로 돈다 — `.env` 없는 작업 디렉터리에서 필수 값 없이 import."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in config.REQUIRED_WITHOUT_ENV_FILE and k != "PYTHONPATH"
    }
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode != 0
    assert ".env 파일이 없고" in result.stderr
