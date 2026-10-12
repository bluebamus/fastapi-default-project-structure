"""``scripts/create_superuser.py`` — 첫 관리자 만들기·승격 (service-hardening ADR-020, ledger F-024).

``main()`` 을 sqlite 파일 DB 세션으로 직접 부른다(``session_factory`` 주입). ``main`` 이 ``asyncio.run`` 으로
자기 이벤트 루프를 돌리므로 테스트는 동기 함수이고, 엔진은 루프마다 새 연결을 여는 ``NullPool`` 을 쓴다.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db.models_registry import import_all_models
from app.core.db.session import Base
from app.core.security.password_hasher import PasswordHasher
from app.features.user.models.models import User
from scripts import create_superuser
from scripts.create_superuser import EXIT_INPUT_ERROR, EXIT_OK, main

import_all_models()

PASSWORD = "s3cret-pass-word"


@pytest.fixture
def db(tmp_path):
    """sqlite 파일 DB 와 commit 횟수를 세는 세션 팩토리."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'su.db'}", poolclass=NullPool)

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    maker = async_sessionmaker(engine, expire_on_commit=False)
    commits = {"count": 0}

    def factory():
        session: AsyncSession = maker()
        original = session.commit

        async def _counting_commit() -> None:
            commits["count"] += 1
            await original()

        session.commit = _counting_commit  # type: ignore[method-assign]
        return session

    def query(statement):
        async def _run():
            async with maker() as session:
                return (await session.execute(statement)).scalars().all()

        return asyncio.run(_run())

    yield factory, query, commits
    asyncio.run(engine.dispose())


def _run(db, *args, stdin_text: str = "") -> int:
    factory, _, _ = db
    return main(list(args), stdin=io.StringIO(stdin_text), session_factory=factory)


def test_creates_superuser_from_stdin_password(db, capsys):
    _, query, commits = db

    code = _run(
        db,
        "--username",
        "admin",
        "--email",
        "admin@example.com",
        "--password-stdin",
        stdin_text=PASSWORD + "\n",
    )

    assert code == EXIT_OK
    [user] = query(select(User))
    assert (user.username, user.email, user.is_superuser, user.is_active) == (
        "admin",
        "admin@example.com",
        True,
        True,
    )
    assert user.hashed_password.startswith("$argon2id$")
    ok, _ = asyncio.run(PasswordHasher().verify_and_update(PASSWORD, user.hashed_password))
    assert ok, "만든 계정으로 로그인할 수 없다"
    assert commits["count"] == 1
    out = capsys.readouterr()
    assert PASSWORD not in out.out + out.err


def test_promotes_existing_user_without_touching_password(db):
    factory, query, commits = db

    async def _seed() -> None:
        async with factory() as session:
            session.add(User(username="kim", email="kim@example.com", hashed_password="keep-me"))
            await session.commit()

    asyncio.run(_seed())
    commits["count"] = 0

    code = _run(db, "--username", "kim")  # 승격은 이메일·비밀번호를 묻지 않는다

    assert code == EXIT_OK
    [user] = query(select(User))
    assert user.is_superuser is True
    assert user.hashed_password == "keep-me"
    assert commits["count"] == 1


def test_interactive_password_is_asked_twice(db, monkeypatch):
    _, query, _ = db
    answers = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr(create_superuser.getpass, "getpass", lambda prompt="": next(answers))

    code = _run(db, "--username", "admin", "--email", "admin@example.com")

    assert code == EXIT_OK
    assert [u.username for u in query(select(User))] == ["admin"]


def test_password_mismatch_creates_nothing(db, monkeypatch):
    _, query, commits = db
    answers = iter([PASSWORD, PASSWORD + "x"])
    monkeypatch.setattr(create_superuser.getpass, "getpass", lambda prompt="": next(answers))

    code = _run(db, "--username", "admin", "--email", "admin@example.com")

    assert code == EXIT_INPUT_ERROR
    assert query(select(User)) == []
    assert commits["count"] == 0


@pytest.mark.parametrize(
    ("args", "stdin_text"),
    [
        (["--username", "admin", "--password-stdin"], PASSWORD + "\n"),  # 이메일 누락
        (["--username", "admin", "--email", "bad", "--password-stdin"], PASSWORD + "\n"),
        (["--username", "admin", "--email", "a@example.com", "--password-stdin"], "short\n"),
    ],
    ids=["missing-email", "invalid-email", "short-password"],
)
def test_invalid_input_exits_1_without_leaking_password(db, capsys, args, stdin_text):
    _, query, _ = db

    code = _run(db, *args, stdin_text=stdin_text)

    assert code == EXIT_INPUT_ERROR
    assert query(select(User)) == []
    out = capsys.readouterr()
    assert stdin_text.strip() not in out.out + out.err


def test_username_is_required():
    with pytest.raises(SystemExit) as exc_info:
        main([], stdin=io.StringIO(""))
    assert exc_info.value.code == 2
