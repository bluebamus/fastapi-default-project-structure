"""MySQL 8.4 ``caching_sha2_password`` 전체 인증의 RSA — ``aiomysql[rsa]`` 로 선언한다 (e2e-policy-2 의존성 통일).

TLS 아닌 연결의 전체 인증은 비밀번호를 서버 공개키(RSA)로 암호화해 보낸다. PyMySQL(aiomysql 의 하부)은 그 RSA 를
``cryptography`` 로 하고, 없으면 접속이 "'cryptography' package is required" 로 실패한다. 이 저장소에서
``cryptography`` 의 유일한 사용처라 직접 의존성이 아니라 드라이버의 공식 추가 옵션(``aiomysql[rsa]`` =
``PyMySQL[rsa]`` = ``cryptography``)으로 선언한다.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _dependencies() -> dict[str, str]:
    """``{패키지 이름: 선언 원문}`` — 이름은 소문자, 추가 옵션·버전 제약 앞까지."""
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["dependencies"]
    return {re.match(r"[A-Za-z0-9_.\-]+", d).group(0).lower(): d for d in declared}


def test_rsa_comes_from_the_driver_extra_not_a_direct_dependency():
    deps = _dependencies()
    assert deps["aiomysql"].startswith("aiomysql[rsa]"), deps["aiomysql"]
    assert "cryptography" not in deps, deps["cryptography"]
    assert "[" not in deps["pymysql"], deps[
        "pymysql"
    ]  # Alembic 이 직접 쓴다 — 선언은 유지, 옵션 없이


def test_pymysql_can_do_the_rsa_exchange():
    import cryptography  # noqa: F401
    from pymysql import _auth

    assert _auth._have_cryptography is True
