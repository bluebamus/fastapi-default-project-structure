"""문서가 보여주는 비밀값은 배포 안전 검사에 **반드시 걸려야** 한다.

**왜 이 검사가 필요한가.** README 가 `MYSQL_PASSWORD=your_password` 를 `.env.example` 의
내용이라며 인용하고 있었다(2026-10-01 발견). 실제 값은 `change-this-mysql-password` 다.
단순 오기가 아니라 **위험한** 오기였다 — `your_password` 는 밑줄 때문에 placeholder 판정의
``your-`` 접두사에 걸리지 않는다. 즉 README 를 따라 그 값을 쓰면 **배포 안전 검사를 그대로
통과해** staging/production 이 교체되지 않은 비밀번호로 떠버린다.

기존 문서 검사들은 경로·심볼·링크의 **존재**만 본다. 문서가 인용한 **값**이 안전한지는
아무도 보지 않았다. 이 검사가 그 구멍을 메운다.

**판정 기준은 문자열 비교가 아니라 `is_placeholder_secret()` 자체다.** `.env.example` 과
글자가 같은지 묻지 않는다 — 문서가 어떤 값을 보여주든, 그 값이 **검증기에 걸리는 값인지**를
묻는다. 그래야 검증기 규칙이 바뀌어도 이 검사가 함께 따라간다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from config import is_placeholder_secret

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 이름이 비밀값을 가리키는 환경변수.
_SECRET_NAME = re.compile(r"(PASSWORD|SECRET|_KEY)$")

#: 이름은 비밀값처럼 보이지만 실제로는 **불리언 플래그**인 것들. 값이 `yes`/`true` 라고
#: 해서 유출이 아니다 — 여기에 넣지 않으면 검사가 헛돌며 빨간불만 낸다.
_NOT_A_SECRET = frozenset(
    {
        "MYSQL_ALLOW_EMPTY_PASSWORD",
        "MYSQL_RANDOM_ROOT_PASSWORD",
    }
)

#: `KEY=value` 꼴. 값에 공백·따옴표·백틱·닫는 괄호가 오면 거기서 끊는다.
_ASSIGNMENT = re.compile(r"\b([A-Z][A-Z0-9_]{2,})=([^\s`'\"|)]*)")

_DOCS = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs" / "guides").glob("*.md"))]


def _secret_assignments(text: str) -> list[tuple[str, str]]:
    return [
        (key, value)
        for key, value in _ASSIGNMENT.findall(text)
        if _SECRET_NAME.search(key) and key not in _NOT_A_SECRET
    ]


@pytest.mark.parametrize("doc", _DOCS, ids=lambda p: p.name)
def test_documented_secret_values_are_rejected_by_the_validator(doc: Path) -> None:
    """문서에 적힌 비밀값은 전부 placeholder 판정에 걸려야 한다."""
    if not doc.exists():
        pytest.skip(f"{doc.name} 없음")

    offenders = [
        f"{key}={value!r}"
        for key, value in _secret_assignments(doc.read_text(encoding="utf-8"))
        if not is_placeholder_secret(value)
    ]

    assert not offenders, (
        f"{doc.name} 이 배포 안전 검사를 **통과해 버리는** 비밀값을 보여준다: {offenders}\n"
        "따라 쓰면 staging/production 이 교체되지 않은 값으로 기동한다. "
        "`change-this-...` 처럼 검증기가 거부하는 값으로 바꿀 것."
    )


def test_env_example_itself_is_all_placeholders() -> None:
    """`.env.example` 의 비밀값도 같은 기준을 지켜야 한다 — 견본이 안전해야 인용도 안전하다.

    주석 처리된 줄도 본다. 주석은 "이렇게 쓰라" 는 예시이고, 주석을 푸는 순간 그 값이
    실제 설정이 된다 — 검증기를 통과하는 값을 그 자리에 두면 안 된다.
    """
    env_example = REPO_ROOT / ".env.example"
    assert env_example.exists(), ".env.example 이 없다"

    # `.env` 는 보지 않는다 — git 에서 제외돼 있고 실제 값이 들어 있을 수 있다.
    offenders = [
        f"{key}={value!r}"
        for key, value in _secret_assignments(env_example.read_text(encoding="utf-8"))
        if not is_placeholder_secret(value)
    ]

    assert not offenders, f".env.example 에 검증기를 통과하는 비밀값이 있다: {offenders}"


def test_the_check_is_not_vacuous() -> None:
    """파싱이 실제로 동작하는지 확인한다 — 정규식이 죽으면 위 검사는 조용히 전부 통과한다.

    기준을 `.env.example` 로 잡는다. 거기에는 비밀 환경변수가 **반드시** 있다.
    README 를 기준으로 삼지 않는 이유: 비밀 예시를 README 에 두는 것은 저장소마다 다른
    선택이고, 안 두는 것이 더 안전하다. 없다고 검사가 고장난 것은 아니다.
    """
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert _secret_assignments(
        env_example
    ), "`.env.example` 에서 비밀 환경변수를 하나도 찾지 못했다 — 파싱이 깨졌다"
