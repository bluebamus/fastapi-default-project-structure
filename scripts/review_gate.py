"""Phase 검수 게이트 — 매 단계 종료 시 실행하는 결정적 점검 (ADR-006).

확률적 리뷰("훑어봤는데 문제없음")는 수렴 증거가 아니다. 여기서는 **실행 결과로만**
판정한다. 하나라도 빨간 항목이 있으면 다음 Phase 로 넘어가지 않는다.

    python scripts/review_gate.py            # 전체
    python scripts/review_gate.py --fast     # 정적 검사만(테스트 제외)

점검 항목 — **번호가 아니라 이름으로 가리킨다.** 검사를 추가할 때마다 번호가 밀려 문서와 어긋나고,
실제로 charter 의 "게이트 검사 12" 와 이 목록의 12번이 서로 다른 검사를 가리킨 적이 있다.

    pytest                      전건 통과. `returncode` 뿐 아니라 요약의 결과 종류도 본다 —
                                `skipped`·`xfailed`·`xpassed`·`deselected` 가 0 이 아니면 실패다(ADR-040)
    ruff check
    ruff format --check
    mypy
    pip-audit                   설치된 의존성에 공개된 취약점 권고가 0건 (ADR-035)
    check_layering              계층 불변식 (INV-1/2/5) 정적 점검
    check_public_api_unchanged  기존 공개 API 불변 (baseline/openapi.json 대비, INV-11)
    check_test_port_single_source
                                MySQL 테스트 포트 단일 출처 (compose·테스트·charter 일치, ADR-008)
                                + 그 값이 3306(공유 인스턴스)이 아님 (C-7)
    check_no_table_drop_in_app  운영 코드(`app/`·`main.py`)에 `drop_all` 이 없음 (C-6 / AR-006)
    check_cited_commits_reachable
                                문서가 인용한 커밋 해시가 HEAD 에서 도달 가능 (ADR-009)
    check_cited_requirement_ids_exist
                                코드·문서가 인용한 요구 ID 가 실제로 선언돼 있음 (ADR-014)
    check_async_path_operations 모든 path operation 이 async 이고 요청 경로에 동기 I/O 가 없음
                                (INV-10/NFR-009)
    check_process_level_tests_collected
                                취소·프로세스 종료 계약 테스트가 삭제·개명되지 않고 수집됨
    check_charter_criteria_closed
                                charter 인수기준이 열린 채로 수렴을 선언하지 않음 (ADR-015)
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


#: pytest 요약에 이것들이 0 이 아닌 개수로 있으면 "돌았는데 통과" 가 아니다.
#: `skipped` 는 인프라가 없어 **안 돈** 것이고, `deselected` 는 전체를 돌린다면서
#: 일부를 골라낸 것이다 — 어느 쪽도 전체 통과의 근거가 될 수 없다(residual-risk R-003).
_BAD_OUTCOMES = ("skipped", "xfailed", "xpassed", "deselected")


#: pytest 는 파이프로 캡처해도 요약에 ANSI 색상 코드를 섞는다. 그대로 두면
#: `\x1b[1m3 skipped` 가 되어 `3` 앞 글자가 `m`(단어 문자)이라 `\b` 가 성립하지
#: 않는다 — 정규식이 **아무것도 못 잡으면서 게이트는 초록**이 된다. 실측으로 확인했다.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _forbidden_outcomes(log: str) -> list[str]:
    """pytest 요약에서 허용하지 않는 결과를 찾는다.

    `1 skipped` 처럼 **0 이 아닌 개수**만 잡는다. `0 skipped` 도 정상 출력에 나오므로
    그것까지 실패로 보면 게이트가 영원히 빨간불이 된다.
    """
    plain = _ANSI.sub("", log)
    return [o for o in _BAD_OUTCOMES if re.search(rf"\b[1-9][0-9]* {o}\b", plain)]


def run_tool(
    name: str, args: list[str], tail_lines: int = 1, *, forbid_skips: bool = False
) -> None:
    proc = subprocess.run(  # noqa: S603
        [str(PYTHON), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    # 한 줄만 보여 주면 pip-audit 처럼 표로 답하는 도구는 **어느 패키지가 걸렸는지**가
    # 잘려 나간다. 실패한 항목만 꼬리를 길게 잡는다(통과 시 출력은 종전대로 없음).
    detail = "" if proc.returncode == 0 else "\n       ".join(tail[-tail_lines:])

    # returncode 가 0 이어도 **안 돈 것**이 섞여 있으면 통과로 보지 않는다. 통과 개수만
    # 읽으면 인프라가 없어 빠진 테스트가 초록 뒤에 숨는다 — 실제로 Redis 포트 하나
    # 때문에 uvicorn 수명주기 3건이 그렇게 빠져 있었다(2026-09-29).
    bad = _forbidden_outcomes(output) if forbid_skips else []
    if bad:
        # `-rsxX` 가 찍은 사유 줄을 함께 보여 준다. 무엇이 왜 안 돌았는지 모르면 고칠 수 없다.
        # 이 줄들도 ANSI 로 시작하므로(`\x1b[33mSKIPPED`) 걷어내고 판별한다.
        plain_tail = [_ANSI.sub("", ln) for ln in tail]
        reasons = [ln for ln in plain_tail if ln.startswith(("SKIPPED", "XFAIL", "XPASS"))]
        detail = f"요약에 {' · '.join(bad)} 가 있다 — 안 돈 것은 통과가 아니다"
        if reasons:
            detail += "\n       " + "\n       ".join(reasons[:10])

    report(name, proc.returncode == 0 and not bad, detail)


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
        # 두 곳 모두 MYSQL_TEST_PORT 로 덮어쓸 수 있다 — 비교 대상은 **기본값**이다.
        _mysql_test_port(REPO_ROOT / "compose.test.yaml", r"\$\{MYSQL_TEST_PORT:-(\d+)\}:3306"),
        _mysql_test_port(
            REPO_ROOT / "tests/integration/conftest.py",
            r'^MYSQL_PORT = int\(os\.getenv\("MYSQL_TEST_PORT", "(\d+)"\)\)',
        ),
        _mysql_test_port(
            REPO_ROOT / "docs/crp/groups/orm-raw-repository/charter.md",
            r"호스트 포트 \*\*(\d+)\*\*",
        ),
    ]
    missing = [name for name, port in sources if port is None]
    ports = {port for _, port in sources if port is not None}
    # C-7 — 테스트가 **공유 인스턴스(3306)** 를 가리키면 안 된다. 같은 값으로 맞춰 놓고
    # 그 값이 3306 이면 단일 출처 판정은 통과하는데 제약은 깨진다. 한 줄로 막는다.
    shared = "3306" in ports
    report(
        "MySQL 테스트 포트 단일 출처 (ADR-008) + 공유 인스턴스 회피 (C-7)",
        not missing and len(ports) == 1 and not shared,
        f"추출실패={missing} 값={sorted(ports)}"
        + (" — 3306 은 공유 인스턴스다(C-7)" if shared else "")
        if (missing or len(ports) != 1 or shared)
        else "",
    )


def check_no_table_drop_in_app() -> None:
    """운영 코드에 테이블 삭제 경로가 없는지 — C-6 (AR-006).

    "shutdown 에서 DB table 을 drop 하지 않는다" 는 §4 의 불가침 제약인데 **강제하는 검사가
    없었다**(2026-10-06 발견). 지금은 `app/` 과 `main.py` 에 `drop_all` 이 0건이라 *코드에
    없어서* 지켜지는 상태다 — 누가 lifespan 종료에 한 줄 넣으면 아무도 못 잡는다. 그게
    통합 테스트 DB 라면 데이터가 사라지고, 운영이라면 사고다.

    ponytail: `drop_all` 이라는 **이름**만 본다. `DROP TABLE` 을 Raw 로 쓰는 경로까지 보려면
    SQL 파서가 필요한데, Raw 문장은 이미 읽기 전용 가드와 `_text_is_write()` 가 보고 있고
    여기서 노리는 사고는 "편의로 `Base.metadata.drop_all` 을 부르는 것" 이다. 필요해지면
    키워드를 늘린다.

    테스트 픽스처는 대상이 아니다 — `tests/integration/conftest.py` 는 매 실행마다 스키마를
    새로 만들어야 해서 drop 이 **설계**다. 그래서 `app/` 과 `main.py` 만 본다.
    """
    offenders: list[str] = []
    targets = [*iter_source_files("app"), REPO_ROOT / "main.py"]
    for path in targets:
        if not path.exists():
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in rel:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "drop_all" in line:
                offenders.append(f"{rel}:{number}")

    report(
        "C-6 운영 코드에 테이블 삭제 없음 (AR-006)",
        not offenders,
        f"`drop_all` {len(offenders)}건: {offenders}"
        if offenders
        else f"검사 {len(targets)}개 파일",
    )


def check_cited_commits_reachable() -> None:
    """CRP 문서가 근거로 인용한 커밋 해시가 HEAD 에서 도달 가능한지 (ADR-009).

    author rewrite 는 인용 해시 12건을 한꺼번에 무효화했고, 그래도 게이트는 초록이었다.
    근거로 못 따라가는 해시는 근거가 아니다. 얕은 클론에서는 판정할 수 없으므로 skip 한다
    — 여기서 억지로 실패시키면 CI 가 오탐으로 빨개지고, 그러면 아무도 안 본다.

    ponytail: **아예 없는 해시는 검사하지 않는다.** 이 저장소에 없는 객체는 Alembic revision
    id 일 수도, 다른 저장소의 커밋일 수도 있어서 구분이 안 된다 — 실제로 `ledger.md` 의 F-024
    비고가 자매 저장소 커밋 하나를 일부러 인용한다. 그래서 "존재하지만 HEAD 에서 끊긴" 해시만
    본다. 없는 해시까지 잡으려면 `migrations/versions/` 의 revision id 를 모아 빼야 하는데,
    지금 그 구멍으로 샌 사례가 없으므로 넣지 않는다.
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

    # 커밋이 아닌 토큰(Alembic revision id 등)은 대상이 아니다.
    commits = [h for h in sorted(cited) if git("cat-file", "-e", f"{h}^{{commit}}").returncode == 0]
    stale = [h for h in commits if git("merge-base", "--is-ancestor", h, "HEAD").returncode != 0]
    report(
        "문서 인용 커밋 도달성 (ADR-009)",
        not stale,
        f"HEAD 에서 도달 불가 {len(stale)}건: {stale}"
        if stale
        # 두 수를 함께 적는다 — 전에는 토큰 수만 적어 실제 검사량보다 커 보였다.
        else f"커밋 {len(commits)}건 검사 (해시꼴 토큰 {len(cited)}건 중)",
    )


# 요구 ID 를 선언하는 문서. 여기 나타나면 "실재하는 근거" 로 본다.
REQUIREMENT_SOURCES = (
    "docs/specs/orm-raw-repository/requirements.md",
    "docs/crp/groups/orm-raw-repository/design-baseline.md",
    "docs/crp/groups/orm-raw-repository/charter.md",
)
REQUIREMENT_ID = re.compile(
    r"\b(?:SCN-(?:ORM|RAW)|ORM-REP|RAW-REP|TX|VIEW|AR|NFR|MIG|DOC|REQ|ADR)-\d{3}\b"
)
# 이 그룹이 생기기 **전** 검수 라운드의 ID 다. 근거 문서가 이 저장소에 없어서 따라갈 수
# 없지만, 고치는 것은 REQ-005 범위 밖이라 수용했다(residual-risk R-007). 새 코드가 이
# 목록에 기대면 안 되므로 늘리지 않는다.
# `ADR-019` 는 2026-10-07 에 빠졌다 — 원 결정을 찾아 design-baseline §3 주석에 옮겨 적어서
# 이제 정식으로 선언된다(ADR-043). 남은 둘은 출처를 찾지 못한 번호다.
LEGACY_UNDECLARED_IDS = frozenset({"REQ-008", "REQ-009"})

# design-baseline 의 두 레지스터는 **자리까지** 본다 (ADR-041). ADR 은 §3, REQ 은 §2.
REGISTER_SECTION = {"REQ": "2", "ADR": "3"}
_SECTION_HEADING = re.compile(r"^##\s*(\d+)\.")


def _register_declared(text: str) -> set[str]:
    """design-baseline 에서 **옳은 절 안에** 적힌 REQ/ADR 만 선언으로 본다 (ADR-041).

    §5 변경 이력이나 §2 의 "연결" 칸처럼 **인용**으로 적힌 번호는 선언이 아니다.
    """
    declared: set[str] = set()
    section = ""
    for line in text.splitlines():
        heading = _SECTION_HEADING.match(line)
        if heading:
            section = heading.group(1)
            continue
        declared.update(
            found
            for found in REQUIREMENT_ID.findall(line)
            if REGISTER_SECTION.get(found[:3]) == section
        )
    return declared


def check_cited_requirement_ids_exist() -> None:
    """코드·문서가 인용한 요구 ID 가 실제로 선언돼 있는지 (ADR-014).

    F-022 로 드러난 세 번째 dangling reference 다 — 포트(F-019)·해시(F-020)에 이어 이번엔
    존재하지 않는 ``SCN-RAW-003`` 을 코드 주석 3곳이 근거로 인용했다. 인용은 읽는 사람이
    **따라갈 수 있을 때만** 근거이고, 따라가 보면 없는 조항은 있는 것보다 나쁘다 —
    근거가 있다고 믿게 만들기 때문이다.

    ADR-041 로 **REQ/ADR 만 절 단위로 좁혔다.** 파일 전역에서 문자열을 찾으면 §2 요구사항
    표에 잘못 적힌 ADR 도 "선언됨" 으로 통과한다 — 실제로 ADR-036~039 가 그 상태였고,
    인용처는 §3 을 찾아가도 번호가 없다. 위 ponytail 주석이 적어 둔 상향 경로("정의 위치만
    파싱하도록 좁힌다")가 바로 이 경우다. 다른 ID 계열(SCN·NFR·TX·AR…)은 표가 아니라
    본문·제목으로 선언되므로 종전대로 "문서에 나타나면 선언" 이다.

    ponytail: 절 단위까지만 본다 — 표 행인지 주석인지는 가리지 않는다. §3 주석에 번호를
    적어 선언을 대신하는 장치가 이미 있고(ADR-019·ADR-041), 그 관례를 깨지 않는 가장 좁은
    규칙이다. 행 단위 파싱이 필요해지면 그때 좁힌다.
    """
    declared: set[str] = set()
    for rel in REQUIREMENT_SOURCES:
        source = REPO_ROOT / rel
        if not source.exists():
            continue
        text = source.read_text(encoding="utf-8")
        found = set(REQUIREMENT_ID.findall(text))
        if source.name == "design-baseline.md":
            found = {i for i in found if i[:3] not in REGISTER_SECTION}
            found |= _register_declared(text)
        declared.update(found)
    declared |= LEGACY_UNDECLARED_IDS

    sites = list(iter_source_files("app", "tests", "migrations", "scripts"))
    sites += [REPO_ROOT / "README.md"]
    sites += sorted((REPO_ROOT / "docs").rglob("*.md"))

    source_names = {Path(rel).name for rel in REQUIREMENT_SOURCES}
    dangling: dict[str, str] = {}
    for path in sites:
        if path.name in source_names or not path.exists():
            continue
        for found in REQUIREMENT_ID.findall(path.read_text(encoding="utf-8")):
            if found not in declared:
                dangling.setdefault(found, str(path.relative_to(REPO_ROOT)).replace("\\", "/"))

    report(
        "인용 요구 ID 실재 (ADR-014)",
        not dangling,
        f"선언되지 않은 ID {len(dangling)}건: {dangling}"
        if dangling
        else f"검사 {len(declared) - len(LEGACY_UNDECLARED_IDS)}건 선언",
    )


HTTP_METHOD_DECORATORS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
# 요청 event loop 를 붙잡는 호출. 짧아 보여도 동시성 전체가 그 시간만큼 멈춘다.
BLOCKING_CALLS = frozenset({"open", "input"})
BLOCKING_ATTR_CALLS = frozenset(
    {("time", "sleep"), ("shutil", "copy"), ("shutil", "copyfile"), ("subprocess", "run")}
)


def _is_path_operation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr in HTTP_METHOD_DECORATORS:
            return True
    return False


def check_async_path_operations() -> None:
    """모든 공개 path operation 이 async 이고 요청 경로에서 동기 I/O 를 하지 않는지 (INV-10/NFR-009).

    charter 는 GATE 3 에서 이 검사를 요구했는데 **실제로는 존재한 적이 없었다**(F-025).
    아홉 라운드가 GATE 3 통과를 선언하는 동안 이 칸만 근거 없이 초록이었다.

    동기 ``def`` path operation 은 FastAPI 가 threadpool 로 넘겨 주므로 **틀리게 동작하지
    않는다** — 그래서 테스트로도 리뷰로도 안 잡힌다. 드러나는 것은 부하가 걸린 뒤
    threadpool 이 마르는 순간이고, 그때는 원인이 이 파일에 있다고 생각하지 않게 된다.
    """
    sync_operations: list[str] = []
    blocking: list[str] = []
    total = 0

    for path in iter_source_files("app"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not _is_path_operation(node):
                continue
            total += 1
            where = f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno}:{node.name}"
            if isinstance(node, ast.FunctionDef):
                sync_operations.append(where)
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                func = sub.func
                if isinstance(func, ast.Name) and func.id in BLOCKING_CALLS:
                    blocking.append(f"{where} -> {func.id}()")
                elif (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and (func.value.id, func.attr) in BLOCKING_ATTR_CALLS
                ):
                    blocking.append(f"{where} -> {func.value.id}.{func.attr}()")

    problems = sync_operations + blocking
    report(
        "INV-10 path operation async + 동기 I/O 부재",
        not problems and total > 0,
        f"동기 def={sync_operations} 블로킹호출={blocking}" if problems else f"검사 {total}건",
    )


def check_charter_criteria_closed() -> None:
    """charter 의 인수기준이 열려 있는데 수렴을 선언하지 않았는지 (F-024).

    charter §3 은 "여기 적힌 것이 합격 기준의 전부" 라고 스스로 선언한 칸이다. 그 칸이
    열린 채로 checklist 가 "미닫힘 항목 0개" 라고 적으면 두 문서가 서로를 반박한다.
    어느 쪽을 믿을지는 읽는 사람이 정하게 되고, 대개 편한 쪽을 믿는다.

    F-019(포트)·F-020(해시)·F-022(요구 ID)에 이은 **네 번째** 문서 정합 결함이다.
    사람이 눈으로 맞추는 절차는 이미 네 번 실패했다.
    """
    charter = REPO_ROOT / "docs/crp/groups/orm-raw-repository/charter.md"
    checklist = REPO_ROOT / "docs/crp/groups/orm-raw-repository/checklist.md"
    if not charter.exists() or not checklist.exists():
        report("charter 인수기준 ↔ 수렴 선언 정합", True, "그룹 문서 없음 — skip")
        return

    inside = False
    open_boxes: list[str] = []
    for line in charter.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.startswith("## 3.")
            continue
        if inside and line.strip().startswith("- [ ]"):
            open_boxes.append(line.strip()[:40])

    converged = "미닫힘 항목 0개" in checklist.read_text(encoding="utf-8")
    report(
        "charter 인수기준 ↔ 수렴 선언 정합",
        not (converged and open_boxes),
        f"수렴 선언 상태인데 charter §3 에 열린 칸 {len(open_boxes)}개: {open_boxes}"
        if (converged and open_boxes)
        else f"열린 칸 {len(open_boxes)}개 · 수렴선언={converged}",
    )


# 이 계열 결함(F-028·F-029·F-038·F-039)은 **단위 테스트로는 보이지 않는다.** 문제가
# lifespan 바깥(프로세스 종료·신호 처리·uvicorn 내부)에 살기 때문이다. 실제로 이 테스트들이
# 생기기 전 391 passed 는 결함 12건을 하나도 잡지 못했다.
# 그래서 "있는지" 를 기계가 본다 — 느리다는 이유로 조용히 지워지면 그 순간 눈이 없어진다.
PROCESS_LEVEL_TESTS = (
    "tests/core/test_resources.py::test_manager_cancellation_still_runs_remaining_cleanup",
    "tests/integration/test_uvicorn_lifecycle.py::test_normal_shutdown_flushes_every_stage_in_order",
    "tests/integration/test_uvicorn_lifecycle.py::test_startup_failure_still_reports_the_cause",
    "tests/integration/test_uvicorn_lifecycle.py::test_uvicorn_cli_also_flushes_the_shutdown_tail",
    "tests/utils/test_logs.py::test_signal_shutdown_still_drains_the_log_listener",
)


def check_process_level_tests_collected() -> None:
    """취소·프로세스 종료 테스트가 실재하고 **수집되는지** (F-028·F-029·F-038·F-039).

    파일 존재만 보면 함수가 지워지거나 이름이 바뀐 것을 놓친다. ``--collect-only`` 로
    node id 단위 수집을 확인하면 삭제·개명·import 실패가 전부 여기서 걸린다.
    """
    completed = subprocess.run(  # noqa: S603
        [str(PYTHON), "-m", "pytest", "--collect-only", "-q", *PROCESS_LEVEL_TESTS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = completed.stdout + completed.stderr
    missing = [node for node in PROCESS_LEVEL_TESTS if node.split("::")[-1] not in output]
    report(
        "취소·프로세스 종료 테스트 실재 (ADR-017/018/022/023)",
        completed.returncode == 0 and not missing,
        f"수집 실패 — 사라졌거나 이름이 바뀌었다: {missing or output.strip()[-300:]}"
        if (completed.returncode != 0 or missing)
        else f"검사 {len(PROCESS_LEVEL_TESTS)}건 전부 수집됨",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="테스트를 건너뛴다")
    args = parser.parse_args()

    print("=" * 70)
    print("Phase 검수 게이트 (ADR-006)")
    print("=" * 70)

    if not args.fast:
        run_tool(
            "pytest",
            # `-rsxX` 는 skip/xfail 의 **사유**를 찍는다. 사유 없이 조용한 skip 만
            # 잡아내면 왜 안 돌았는지 알 수 없어 고칠 수가 없다.
            ["-m", "pytest", "-q", "-rsxX", "--basetemp", ".pytest_tmp"],
            tail_lines=15,
            forbid_skips=True,
        )
    run_tool("ruff check", ["-m", "ruff", "check", "."])
    run_tool("ruff format --check", ["-m", "ruff", "format", "--check", "."])
    run_tool("mypy", ["-m", "mypy", ".", "--cache-dir", ".mypy_tmp"])
    # 의존성 권고는 코드가 바뀌지 않아도 **밖에서** 늘어난다. 게이트 밖에 두면
    # 초록불 아래에서 조용히 쌓인다 — 실제로 19건이 그렇게 쌓였다(ADR-034/035).
    run_tool(
        "의존성 취약점 0건 (ADR-035)",
        ["-m", "pip_audit", "--strict", "--progress-spinner", "off"],
        tail_lines=30,
    )
    check_layering()
    check_public_api_unchanged()
    check_test_port_single_source()
    check_no_table_drop_in_app()
    check_cited_commits_reachable()
    check_cited_requirement_ids_exist()
    check_async_path_operations()
    check_process_level_tests_collected()
    check_charter_criteria_closed()

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
