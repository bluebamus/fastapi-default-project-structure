"""Phase 검수 게이트 — 매 단계 종료 시 실행하는 결정적 점검 (ADR-006).

확률적 리뷰("훑어봤는데 문제없음")는 수렴 증거가 아니다. 여기서는 **실행 결과로만**
판정한다. 하나라도 빨간 항목이 있으면 다음 Phase 로 넘어가지 않는다.

    python scripts/review_gate.py            # 전체
    python scripts/review_gate.py --fast     # 정적 검사만(테스트 제외)

점검 항목:
    1. pytest 전건 통과
    2. ruff check
    3. ruff format --check
    4. mypy
    5. 계층 불변식 (INV-1/2/5) 정적 점검
    6. 기존 공개 API 불변 (baseline/openapi.json 대비, INV-11)
    7. MySQL 테스트 포트 단일 출처 (compose·테스트·charter 일치, ADR-008)
    8. 문서가 인용한 커밋 해시가 HEAD 에서 도달 가능 (ADR-009)
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess  # noqa: S404 - 품질 도구를 순차 실행하는 검수 하네스
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():  # POSIX
    PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

BASELINE_OPENAPI = REPO_ROOT / "docs/crp/groups/orm-raw-repository/baseline/openapi.json"

SKIP_PARTS = {
    ".venv",
    ".mypy_cache",
    ".mypy_tmp",
    ".pytest_cache",
    ".pytest_tmp",
    ".ruff_cache",
    "__pycache__",
}

failures: list[str] = []

# Windows 콘솔 기본 코드페이지(cp949)로는 한글·em dash 를 못 쓴다. 게이트가 **실패를
# 보고하려는 순간** UnicodeEncodeError 로 죽으면, 초록일 때만 동작하는 게이트가 된다.
# 표준 출력 자체를 UTF-8 로 바꾸고, 그마저 안 되면 대체문자로라도 반드시 보고한다.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        _reconfigure(encoding="utf-8", errors="replace")


def report(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}{'  - ' + detail if detail else ''}")
    if not ok:
        failures.append(f"{name}: {detail}" if detail else name)


def run_tool(name: str, args: list[str]) -> None:
    proc = subprocess.run(  # noqa: S603
        [str(PYTHON), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    report(name, proc.returncode == 0, "" if proc.returncode == 0 else (tail[-1] if tail else ""))


def iter_source_files(*relative: str):
    for rel in relative:
        base = REPO_ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if SKIP_PARTS & set(path.parts):
                continue
            yield path


# =============================================================================
# 5. 계층 불변식
# =============================================================================
def check_layering() -> None:
    """INV-1/2/5 — 계층 책임 위반을 소스에서 직접 찾는다."""
    view_offenders: list[str] = []
    commit_offenders: list[str] = []

    for path in iter_source_files("app/features"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if "/tests/" in rel:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        is_view = "/api/routers/" in rel
        is_dependency = "/dependencies/" in rel
        is_repository = "/repositories/" in rel

        for node in ast.walk(tree):
            # INV-1: View/Service 가 session.execute() 를 직접 호출하지 않는다.
            if isinstance(node, ast.Attribute) and node.attr == "execute" and is_view:
                view_offenders.append(f"{rel}:{node.lineno} execute() 직접 호출")
            # INV-2: Repository·Dependency 는 commit 하지 않는다.
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "commit"
                and (is_repository or is_dependency)
            ):
                commit_offenders.append(f"{rel}:{node.lineno} commit() 호출")

    # View 가 AsyncSession 을 직접 주입받지 않는다.
    session_in_view: list[str] = []
    for path in iter_source_files("app/features"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/api/routers/" not in rel or "/tests/" in rel:
            continue
        if "AsyncSession" in path.read_text(encoding="utf-8"):
            session_in_view.append(rel)

    report(
        "INV-1 View 가 SQL/세션을 직접 다루지 않음",
        not view_offenders and not session_in_view,
        "; ".join(view_offenders + session_in_view),
    )
    report(
        "INV-2 Repository/Dependency commit 없음", not commit_offenders, "; ".join(commit_offenders)
    )

    # INV-5: Raw Base 가 ORM Base 를 상속하지 않는다.
    #
    # 문자열 검색으로 보면 "BaseRepository 를 상속하지 않는다"라고 적은 docstring
    # 까지 위반으로 잡힌다. 실제 클래스 정의의 base 목록만 본다.
    raw_bases = {
        "app/core/repositories/raw_repository_base.py": "RawRepositoryBase",
        "app/core/repositories/raw_crud_base.py": "RawCRUDBase",
    }
    orm_base_names = {"BaseRepository", "CRUDBase"}
    offenders: list[str] = []
    checked = 0

    for rel, class_name in raw_bases.items():
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        checked += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ClassDef) and node.name == class_name):
                continue
            for base in node.bases:
                name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                if name in orm_base_names:
                    offenders.append(f"{rel}: {class_name} -> {name}")

    if checked:
        report("INV-5 Raw Base 가 ORM Base 를 상속하지 않음", not offenders, "; ".join(offenders))
    else:
        print("[SKIP] INV-5 — Raw Base 파일 아직 없음 (Phase 4)")


# =============================================================================
# 6. 기존 공개 API 불변
# =============================================================================
def check_public_api_unchanged() -> None:
    """INV-11 — 기준선의 operation 이 경로·메서드·성공 상태코드까지 그대로인지."""
    if not BASELINE_OPENAPI.exists():
        print("[SKIP] INV-11 — 기준선 openapi.json 없음")
        return

    # 설정은 config.py 만 환경변수를 직접 읽는다는 계약이 있으므로 여기서 DEBUG 를
    # 건드리지 않는다. DEBUG 는 openapi_url 이 서빙되는지에만 영향을 주고
    # app.openapi() 가 만드는 스펙 내용은 바꾸지 않는다.
    proc = subprocess.run(  # noqa: S603
        [
            str(PYTHON),
            "-c",
            "import json;import main;print('__SPEC__'+json.dumps(main.app.openapi()))",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    marker = "__SPEC__"
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith(marker)), None)
    if line is None:
        report("INV-11 기존 공개 API 불변", False, "현재 OpenAPI 를 얻지 못함")
        return

    current = json.loads(line[len(marker) :])
    baseline = json.loads(BASELINE_OPENAPI.read_text(encoding="utf-8"))

    def operations(spec: dict) -> dict[tuple[str, str], set[str]]:
        methods = ("get", "post", "put", "patch", "delete", "head")
        return {
            (method.upper(), path): {
                code for code in operation.get("responses", {}) if code.startswith("2")
            }
            for path, item in spec["paths"].items()
            for method, operation in item.items()
            if method in methods
        }

    base_ops = operations(baseline)
    current_ops = operations(current)

    removed = sorted(set(base_ops) - set(current_ops))
    changed = sorted(
        f"{m} {p} {sorted(base_ops[(m, p)])} -> {sorted(current_ops[(m, p)])}"
        for (m, p) in set(base_ops) & set(current_ops)
        if base_ops[(m, p)] != current_ops[(m, p)]
    )

    report(
        "INV-11 기존 공개 API 불변",
        not removed and not changed,
        f"제거됨={removed} 상태코드변경={changed}",
    )

    added = sorted(set(current_ops) - set(base_ops))
    if added:
        print(f"       (신규 operation {len(added)}건: {added})")


def _mysql_test_port(source: Path, pattern: str) -> tuple[str, str | None]:
    """`source` 에서 `pattern` 으로 포트 하나를 뽑는다. 없으면 (경로, None)."""
    match = re.search(pattern, source.read_text(encoding="utf-8"), re.MULTILINE)
    return (source.name, match.group(1) if match else None)


def check_test_port_single_source() -> None:
    """MySQL 통합 테스트 포트가 compose·테스트·계약서에서 같은 값인지 (ADR-008/009).

    F-012 가 3307 을 3308 로 옮겼는데 charter 와 ADR 은 3307 로 남았다. 어긋난 계약서는
    "이 포트로 뜬다"고 믿게 만들고, 실제로는 **다른 MySQL 에 붙어도** 조용하다. 사람이
    눈으로 맞추는 절차는 이미 한 번 실패했으므로 여기서 기계로 잡는다.
    """
    sources = [
        _mysql_test_port(REPO_ROOT / "compose.test.yaml", r'"(\d+):3306"'),
        _mysql_test_port(REPO_ROOT / "tests/integration/conftest.py", r"^MYSQL_PORT = (\d+)"),
        _mysql_test_port(
            REPO_ROOT / "docs/crp/groups/orm-raw-repository/charter.md",
            r"호스트 포트 \*\*(\d+)\*\*",
        ),
    ]
    missing = [name for name, port in sources if port is None]
    ports = {port for _, port in sources if port is not None}
    report(
        "MySQL 테스트 포트 단일 출처 (ADR-008)",
        not missing and len(ports) == 1,
        f"추출실패={missing} 값={sorted(ports)}" if (missing or len(ports) != 1) else "",
    )


def check_cited_commits_reachable() -> None:
    """CRP 문서가 근거로 인용한 커밋 해시가 HEAD 에서 도달 가능한지 (ADR-009).

    author rewrite 는 인용 해시 12건을 한꺼번에 무효화했고, 그래도 게이트는 초록이었다.
    근거로 못 따라가는 해시는 근거가 아니다. 얕은 클론에서는 판정할 수 없으므로 skip 한다
    — 여기서 억지로 실패시키면 CI 가 오탐으로 빨개지고, 그러면 아무도 안 본다.
    """

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8"
        )

    if git("rev-parse", "--git-dir").returncode != 0:
        report("문서 인용 커밋 도달성 (ADR-009)", True, "git 저장소 아님 — skip")
        return
    if git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        report("문서 인용 커밋 도달성 (ADR-009)", True, "얕은 클론 — skip")
        return

    cited: set[str] = set()
    for doc in sorted((REPO_ROOT / "docs/crp/groups").rglob("*.md")):
        cited.update(re.findall(r"`([0-9a-f]{7,40})`", doc.read_text(encoding="utf-8")))

    stale = [
        h
        for h in sorted(cited)
        # 커밋이 아닌 토큰(Alembic revision id 등)은 대상이 아니다.
        if git("cat-file", "-e", f"{h}^{{commit}}").returncode == 0
        and git("merge-base", "--is-ancestor", h, "HEAD").returncode != 0
    ]
    report(
        "문서 인용 커밋 도달성 (ADR-009)",
        not stale,
        f"HEAD 에서 도달 불가 {len(stale)}건: {stale}" if stale else f"검사 {len(cited)}건",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="테스트를 건너뛴다")
    args = parser.parse_args()

    print("=" * 70)
    print("Phase 검수 게이트 (ADR-006)")
    print("=" * 70)

    if not args.fast:
        run_tool("pytest", ["-m", "pytest", "-q", "--basetemp", ".pytest_tmp"])
    run_tool("ruff check", ["-m", "ruff", "check", "."])
    run_tool("ruff format --check", ["-m", "ruff", "format", "--check", "."])
    run_tool("mypy", ["-m", "mypy", ".", "--cache-dir", ".mypy_tmp"])
    check_layering()
    check_public_api_unchanged()
    check_test_port_single_source()
    check_cited_commits_reachable()

    print("=" * 70)
    if failures:
        print(f"게이트 실패 {len(failures)}건:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("게이트 전건 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
