"""커버리지 하한의 단일 출처 — log-redaction ADR-005.

사용자 결정: 하한 기본값은 0%(측정·리포트만). 필요해지면 ``pyproject.toml`` 의 ``fail_under`` 하나만 올린다.
명령줄에 ``--cov-fail-under`` 가 생기면 그 값이 pyproject 를 덮어 정본이 둘이 된다.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
GATE = ROOT / "scripts" / "review_gate.py"
PYPROJECT = ROOT / "pyproject.toml"


def _commands(path: Path) -> list[str]:
    """주석이 아닌 줄 — 이유를 설명하는 주석에는 옵션 이름이 나와도 된다."""
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]


def test_fail_under_is_declared_once_with_default_zero():
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    assert config["tool"]["coverage"]["report"]["fail_under"] == 0
    assert not any(
        "--cov-fail-under" in opt for opt in config["tool"]["pytest"]["ini_options"]["addopts"]
    )


def test_no_command_line_threshold_overrides_pyproject():
    for path in (CI, GATE):
        offenders = [line for line in _commands(path) if "--cov-fail-under" in line]
        assert not offenders, f"{path.name} 이 하한을 명령줄로 덮는다: {offenders}"


def test_ci_measures_and_prints_coverage():
    runs = [line for line in _commands(CI) if "-m pytest" in line and '-m "not mysql"' in line]

    assert len(runs) == 1, runs
    assert "--cov=app" in runs[0]
    # 자식 프로세스(uvicorn·subprocess 테스트)도 branch 데이터를 쓰게 한다 — 없으면 결합 단계가
    # "Can't combine branch coverage data with statement data" 로 INTERNALERROR 를 낸다.
    assert "--cov-branch" in runs[0]
    assert "--cov-report=term-missing" in runs[0]
    # skip-covered 는 "N files skipped due to complete coverage" 를 찍어 CI 의 SKIP 판정에 걸린다.
    assert "skip-covered" not in runs[0]
