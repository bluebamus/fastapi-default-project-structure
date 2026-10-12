"""첫 관리자 만들기 — Django ``createsuperuser`` 와 같은 운영 도구 (service-hardening ADR-020).

**배포 전에 실행한다.** 여기서 만든(또는 승격한) 슈퍼유저는 API 의 슈퍼유저 전용 경로를 쓰는 계정이자
관리 화면(``/admin``) 로그인 계정이다(admin-login ADR-001 — 관리 화면은 활성 슈퍼유저만 들어간다).
관리 화면을 끈 배포(``ADMIN_DISABLED=true``)에서도 API 관리 경로용으로 필요하다.

API 로 슈퍼유저를 만들려면 이미 슈퍼유저가 있어야 한다(``POST /users`` 는 슈퍼유저 전용). 그 부트스트랩
문제를 서버 밖에서 푼다 — DB 에 직접 붙어 사용자를 만들거나, 이미 있는 사용자를 승격한다::

    uv run python -m scripts.create_superuser --username admin --email admin@example.com
    printf '%s\\n' "$ADMIN_PASSWORD" | uv run python -m scripts.create_superuser \\
        --username admin --email admin@example.com --password-stdin

- 사용자가 없으면: 비밀번호를 받아(대화형 ``getpass`` 두 번, 또는 ``--password-stdin`` 한 줄) Argon2 로
  해시해 **슈퍼유저**로 만든다. 입력 규칙은 API 의 사용자 생성 스키마(``UserCreate``)와 같다.
- 사용자가 있으면: ``is_superuser`` 만 켠다(승격). 비밀번호·이메일은 바꾸지 않는다.

조립은 앱과 같은 부품으로 한다 — 세션은 ``background_db_session``(요청 밖 세션), 해시기는 core provider
``get_password_hasher``, 저장은 ``UserRepository``. 커밋은 끝에 한 번. 비밀번호는 출력·로그에 싣지
않는다(검증 오류도 필드와 사유만 출력한다). 환경 변수는 직접 읽지 않는다 — DB 접속은 ``config`` 가
정한다(설정 계약: ``config.py`` 만 환경을 읽는다).

종료 코드: 0 생성·승격 성공 · 1 입력 오류(이메일 누락·비밀번호 불일치·규칙 위반) · 2 인자 오류(argparse).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import TextIO

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import background_db_session, dispose_engine
from app.core.security.dependencies import get_password_hasher
from app.features.user.repositories.user_repository import UserRepository
from app.features.user.schemas.user_schema import UserCreate

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

EXIT_OK = 0
EXIT_INPUT_ERROR = 1


class InputError(Exception):
    """사용자 입력이 규칙에 맞지 않는다(종료 코드 1)."""


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.create_superuser",
        description="슈퍼유저를 만들거나 기존 사용자를 슈퍼유저로 승격한다.",
    )
    parser.add_argument("--username", required=True, help="사용자명")
    parser.add_argument("--email", help="이메일(새로 만들 때 필수)")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="비밀번호를 표준 입력 한 줄에서 읽는다(자동화용). 없으면 대화형으로 두 번 묻는다.",
    )
    return parser.parse_args(argv)


def _read_password(from_stdin: bool, stdin: TextIO) -> str:
    if from_stdin:
        return stdin.readline().rstrip("\r\n")
    password = getpass.getpass("비밀번호: ")
    if password != getpass.getpass("비밀번호 확인: "):
        raise InputError("비밀번호가 일치하지 않습니다.")
    return password


def _validated(args: argparse.Namespace, password: str) -> UserCreate:
    if not args.email:
        raise InputError("새 사용자를 만들려면 --email 이 필요합니다.")
    try:
        return UserCreate(
            username=args.username, email=args.email, password=password, is_superuser=True
        )
    except ValidationError as exc:
        # str(exc) 에는 입력값(비밀번호)이 실린다 — 필드와 사유만 낸다.
        reasons = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise InputError(f"입력이 올바르지 않습니다 — {reasons}") from None


async def _run(args: argparse.Namespace, stdin: TextIO, session_factory: SessionFactory) -> str:
    async with session_factory() as db_session:
        users = UserRepository(db_session)
        existing = await users.get_by_username(args.username)
        if existing is not None:
            await users.update_by_id(existing.id, {"is_superuser": True})
            message = f"기존 사용자 '{existing.username}' 를 슈퍼유저로 승격했습니다."
        else:
            data = _validated(args, _read_password(args.password_stdin, stdin))
            hashed = await get_password_hasher().hash(data.password)
            created = await users.create(
                {**data.model_dump(exclude={"password"}), "hashed_password": hashed}
            )
            message = f"슈퍼유저 '{created.username}' 를 만들었습니다(id={created.id})."
        await db_session.commit()
    return message


async def _run_with_app_engine(args: argparse.Namespace, stdin: TextIO) -> str:
    try:
        return await _run(args, stdin, background_db_session)
    finally:
        await dispose_engine()


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    session_factory: SessionFactory | None = None,
) -> int:
    """CLI 진입점. 테스트는 ``session_factory`` 로 다른 DB 의 세션을 넣는다."""
    # Windows 콘솔(cp949)에서 출력 문자 하나로 죽지 않게 한다 — DB 는 이미 바뀐 뒤일 수 있다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = _parse_args(argv)
    source = stdin if stdin is not None else sys.stdin
    try:
        if session_factory is None:
            message = asyncio.run(_run_with_app_engine(args, source))
        else:
            message = asyncio.run(_run(args, source, session_factory))
    except InputError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    print(message)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
