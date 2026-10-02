"""게이트의 레지스터 **자리** 판정 — `_register_declared()` (ADR-041).

**이 테스트가 지키는 것.** design-baseline 에는 레지스터가 둘이다 — §2 는 요구사항(REQ),
§3 은 설계 결정(ADR). 두 표가 **둘 다 6열** 이라 ADR 행이 §2 에 들어가도 마크다운은 멀쩡히
렌더링된다. 실제로 ADR-036~039 가 그 상태였고, 인용처(`ARCHITECTURE.md` · `DEVELOPMENT.md` ·
`tests/core/test_router_raw_dml.py` · `residual-risk.md`)가 §3 을 찾아가면 035 다음이 040 이라
번호가 없다. **표가 깨지지 않는 오류라 눈으로는 보이지 않는다** — 기계만 볼 수 있다.

**왜 "절" 까지만 보는가.** §3 은 표 뒤 주석에 번호를 적어 선언을 대신하는 관례가 이미
있다(ADR-019 · ADR-041). 행 단위로 파싱하면 그 관례가 깨진다. 그래서 판정은 "옳은 절 안에
나타나는가" 이고, 인용(§5 변경 이력, §2 의 `연결` 칸)은 선언으로 세지 않는다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from review_gate import _register_declared  # noqa: E402

BASELINE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "crp"
    / "groups"
    / "orm-raw-repository"
    / "design-baseline.md"
)

WELL_FORMED = """\
## 2. 요구사항 레지스터

| Req-ID | 날짜 | 요청 | 도출 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | d | r | o | Active | ADR-001 |

## 3. 설계 결정 기록

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | d | decision | why | Accepted | — |

## 5. 변경 이력

- v0.1: REQ-002 · ADR-002 등록.
"""


def test_each_register_declares_only_its_own_kind() -> None:
    assert _register_declared(WELL_FORMED) == {"REQ-001", "ADR-001"}


def test_a_citation_in_the_change_log_is_not_a_declaration() -> None:
    """§5 가 번호를 언급해도 선언이 아니다 — 아니면 오타가 스스로를 선언한다."""
    declared = _register_declared(WELL_FORMED)
    assert "REQ-002" not in declared
    assert "ADR-002" not in declared


def test_the_link_column_of_the_requirement_table_is_not_a_declaration() -> None:
    """§2 의 `연결` 칸에 적힌 ADR-001 은 §2 안이므로 선언으로 세지 않는다."""
    only_requirements = WELL_FORMED.split("## 3.")[0]
    assert _register_declared(only_requirements) == {"REQ-001"}


#: 가짜 ID 는 **글자 그대로 적지 않는다** — 적는 순간 게이트의 "인용 요구 ID 실재" 검사가
#: 이 파일을 인용처로 보고 선언되지 않은 ID 라며 떨어진다. 조립해서 쓴다.
FAKE_ADR = "ADR-" + "099"


def test_an_adr_row_misfiled_into_the_requirement_table_is_not_declared() -> None:
    """이 테스트가 ADR-041 의 본체다 — 좁히기 전에는 이게 통과해 버렸다."""
    misfiled = WELL_FORMED.replace(
        "| REQ-001 | d | r | o | Active | ADR-001 |",
        f"| REQ-001 | d | r | o | Active | ADR-001 |\n"
        f"| {FAKE_ADR} | d | decision | why | Accepted | — |",
    )
    assert FAKE_ADR not in _register_declared(misfiled)


def test_the_real_baseline_declares_the_misfiled_adrs_through_the_section_note() -> None:
    """ADR-036~039 는 §2 표에 있지만 §3 주석이 번호를 적어 선언을 잇는다(ADR-041)."""
    declared = _register_declared(BASELINE.read_text(encoding="utf-8"))
    assert {"ADR-036", "ADR-037", "ADR-038", "ADR-039"} <= declared, (
        "§3 의 ADR-041 주석이 네 번호를 적고 있어야 한다 — "
        "주석을 지우면 인용처(ARCHITECTURE·DEVELOPMENT·residual-risk·테스트)가 dangling 이 된다"
    )


def test_the_check_is_not_vacuous() -> None:
    """실제 문서에서 양쪽 레지스터가 모두 걸리는지 — 파싱이 죽으면 위가 전부 통과한다."""
    declared = _register_declared(BASELINE.read_text(encoding="utf-8"))
    assert sum(i.startswith("REQ-") for i in declared) >= 20
    assert sum(i.startswith("ADR-") for i in declared) >= 30
