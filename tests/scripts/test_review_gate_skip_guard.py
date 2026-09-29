"""게이트의 "조용한 skip 거부" 판정 — `_forbidden_outcomes()`.

**이 테스트가 지키는 것.** 게이트가 `returncode == 0` 만 보면, 인프라가 없어 *안 돈*
테스트가 초록 뒤에 숨는다. 실제로 Redis 포트 환경변수 하나 때문에 uvicorn 수명주기
테스트 3건이 그렇게 빠진 채 게이트가 통과한 적이 있다(2026-09-29, residual-risk R-003 계열).

**왜 색상 케이스가 핵심인가.** pytest 는 파이프로 캡처해도 요약에 ANSI 색상 코드를
섞는다. 그러면 요약이 ``\x1b[1m3 skipped`` 가 되어 `3` 앞 글자가 `m`(단어 문자)이라
``\b`` 가 성립하지 않는다. 평문 요약으로만 시험하면 **판정이 실전에서 아무것도 못
잡는데도 테스트는 초록**이다 — 이 판정을 처음 넣었을 때 정확히 그 상태였고, 게이트를
실제로 돌려 보고서야 드러났다. 그래서 여기서는 **진짜 출력 모양**으로 시험한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from review_gate import _forbidden_outcomes  # noqa: E402

# 실제 pytest 출력 모양(색상 포함).
COLORED_SKIP = (
    "\x1b[33m===== \x1b[32m609 passed\x1b[0m, \x1b[33m\x1b[1m3 skipped\x1b[0m\x1b[33m in 36s\x1b[0m"
)
COLORED_CLEAN = (
    "\x1b[33m===== \x1b[32m612 passed\x1b[0m, \x1b[33m1 warning\x1b[0m\x1b[33m in 32s\x1b[0m"
)


@pytest.mark.parametrize(
    "summary",
    [
        COLORED_SKIP,
        "609 passed, 3 skipped, 1 warning in 28s",
        "5 passed, 2 xfailed",
        "5 passed, 1 xpassed",
        "788 passed, 32 deselected",
    ],
    ids=["colored-skip", "plain-skip", "xfailed", "xpassed", "deselected"],
)
def test_not_run_is_not_a_pass(summary: str) -> None:
    """안 돈 것은 통과가 아니다 — 색상이 섞여도 잡아야 한다."""
    assert _forbidden_outcomes(summary), f"잡히지 않았다: {summary!r}"


@pytest.mark.parametrize(
    "summary",
    [
        COLORED_CLEAN,
        "612 passed, 1 warning in 32s",
        # `0 skipped` 는 정상 출력이다. 이걸 실패로 보면 게이트가 영원히 빨간불이 된다.
        "100 passed, 0 skipped",
        "\x1b[1m0 skipped\x1b[0m",
        "no tests ran",
    ],
    ids=["colored-clean", "plain-clean", "zero-skipped", "colored-zero", "no-tests"],
)
def test_clean_summary_is_not_a_false_positive(summary: str) -> None:
    """반대 방향도 지킨다 — 멀쩡한 요약을 실패로 만들면 게이트를 아무도 안 믿는다."""
    assert _forbidden_outcomes(summary) == [], f"오탐: {summary!r}"
