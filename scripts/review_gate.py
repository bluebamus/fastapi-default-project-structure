"""품질 게이트 — 실행 결과로만 판정하는 결정적 점검. 하나라도 FAIL 이면 종료 코드 1.

    uv run python -m scripts.review_gate            # 전체
    uv run python -m scripts.review_gate --fast     # pytest 제외 (CI 는 pytest 를 별도 단계로 돌린다)

점검 항목:

    pytest                      전건 통과. 요약에 `skipped`·`xfailed`·`xpassed`·`deselected` 가 있어도 실패
    ruff check · ruff format --check · mypy
    pip-audit                   설치된 의존성에 공개된 취약점 권고가 0건
    check_layering              View 가 SQL/세션을 직접 다루지 않음, Repository·Dependency 가 commit 하지 않음,
                                Raw Base 가 ORM Base 를 상속하지 않음
    check_public_api_unchanged  tests/openapi_baseline.json 의 operation 이 경로·메서드·성공 상태코드까지 그대로
    check_no_table_drop_in_app  운영 코드(`app/`·`main.py`)에 `drop_all` 이 없음
    check_no_empty_python_files 내용 없는 .py 가 없음 (`__init__.py` 제외)
    check_async_path_operations 모든 path operation 이 async 이고 요청 경로에 동기 I/O 가 없음
    check_process_level_tests_collected
                                취소·프로세스 종료 테스트가 삭제·개명되지 않고 수집됨
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

BASELINE_OPENAPI = REPO_ROOT / "tests/openapi_baseline.json"

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
#: 일부를 골라낸 것이다 — 어느 쪽도 전체 통과의 근거가 될 수 없다.
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


def _tracked_files(root: Path) -> list[Path] | None:
    """git 이 추적하는 파일 목록. git 을 쓸 수 없으면(저장소 아님·git 없음) ``None``.

    ``-z`` 는 경로를 NUL 로 끊고 따옴표·이스케이프를 하지 않는다 — 한글 경로가 그대로 온다.
    """
    try:
        completed = subprocess.run(  # noqa: S603
            ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [root / name for name in completed.stdout.decode("utf-8").split("\0") if name]


def repo_files(rel: str, suffix: str, *, root: Path = REPO_ROOT) -> list[Path]:
    """``root/rel`` 아래에서 ``suffix`` 로 끝나는 파일 — **git 이 추적하는 것만** 본다.

    작업 트리를 rglob 으로 훑으면 추적되지 않는 로컬 파일(다른 도구의 보고서·임시 스크립트)이
    판정에 섞여 로컬과 CI 의 결과가 달라진다. git 을 쓸 수 없을 때만
    rglob 으로 대신한다. 인덱스에는 있지만 지운 파일은 뺀다.
    """
    base = root / rel
    tracked = _tracked_files(root)
    if tracked is None:
        candidates = list(base.rglob(f"*{suffix}")) if base.exists() else []
    else:
        candidates = [path for path in tracked if path.is_relative_to(base)]
    return sorted(
        path
        for path in candidates
        # 루트 기준 상대 경로만 본다 — 루트 자체가 `.pytest_tmp` 아래(게이트의 --basetemp)면 전부 걸러졌다.
        if path.suffix == suffix
        and path.is_file()
        and not SKIP_PARTS & set(path.relative_to(root).parts)
    )


def iter_source_files(*relative: str):
    for rel in relative:
        yield from repo_files(rel, ".py")


# =============================================================================
# 5. 계층 불변식
# =============================================================================
def check_layering() -> None:
    """계층 책임 위반을 소스에서 직접 찾는다."""
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
            # View 가 session.execute() 를 직접 호출하지 않는다.
            if isinstance(node, ast.Attribute) and node.attr == "execute" and is_view:
                view_offenders.append(f"{rel}:{node.lineno} execute() 직접 호출")
            # Repository·Dependency 는 commit 하지 않는다.
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
        "계층: View 가 SQL/세션을 직접 다루지 않음",
        not view_offenders and not session_in_view,
        "; ".join(view_offenders + session_in_view),
    )
    report(
        "계층: Repository/Dependency commit 없음", not commit_offenders, "; ".join(commit_offenders)
    )

    # Raw Base 가 ORM Base 를 상속하지 않는다.
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
        report("계층: Raw Base 가 ORM Base 를 상속하지 않음", not offenders, "; ".join(offenders))
    else:
        report("계층: Raw Base 가 ORM Base 를 상속하지 않음", False, "Raw Base 파일이 없다")


# =============================================================================
# 6. 기존 공개 API 불변
# =============================================================================
def check_public_api_unchanged() -> None:
    """기준선의 operation 이 경로·메서드·성공 상태코드까지 그대로인지."""
    if not BASELINE_OPENAPI.exists():
        report("기존 공개 API 불변", False, f"기준선 없음: {BASELINE_OPENAPI}")
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
        report("기존 공개 API 불변", False, "현재 OpenAPI 를 얻지 못함")
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
        "기존 공개 API 불변",
        not removed and not changed,
        f"제거됨={removed} 상태코드변경={changed}",
    )

    added = sorted(set(current_ops) - set(base_ops))
    if added:
        print(f"       (신규 operation {len(added)}건: {added})")


def empty_python_files(root: Path = REPO_ROOT) -> list[Path]:
    """git 이 추적하는 내용 없는 ``.py`` — ``__init__.py`` 는 패키지 표식이라 비어 있어도 된다."""
    return [
        path
        for path in repo_files(".", ".py", root=root)
        if path.name != "__init__.py" and path.stat().st_size == 0
    ]


def check_no_empty_python_files() -> None:
    """빈 모듈·빈 테스트 파일이 없는지.

    빈 ``test_db.py`` 는 테스트가 있는 것처럼 보이게 하고, 빈 모듈은 "여기 뭔가 있어야 하나"
    를 묻게 한다 — 2026-11-11 에 기능 자리채움으로 남은 12개를 지우며 재발을 막으려 둔다.
    """
    empty = [path.relative_to(REPO_ROOT).as_posix() for path in empty_python_files()]
    report(
        "빈 .py 파일 없음 (__init__.py 제외)",
        not empty,
        f"내용 없는 파일 {len(empty)}건 — 쓰지 않으면 지운다: {empty}" if empty else "",
    )


def check_no_table_drop_in_app() -> None:
    """운영 코드에 테이블 삭제 경로가 없는지.

    누가 lifespan 종료에 `Base.metadata.drop_all` 한 줄을 넣으면 운영 데이터가 사라진다.

    shortcut: `drop_all` 이라는 **이름**만 본다. `DROP TABLE` 을 Raw 로 쓰는 경로까지 보려면
    SQL 파서가 필요한데, Raw 문장은 이미 읽기 전용 가드와 `_text_is_write()` 가 보고 있고
    여기서 노리는 사고는 "편의로 `Base.metadata.drop_all` 을 부르는 것" 이다. 필요해지면
    키워드를 늘린다.

    테스트 픽스처는 대상이 아니다 — 매 실행마다 스키마를 새로 만들어야 해서 drop 이
    **설계**다. 그래서 `app/` 과 `main.py` 만 본다.
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
        "운영 코드에 테이블 삭제 없음",
        not offenders,
        f"`drop_all` {len(offenders)}건: {offenders}"
        if offenders
        else f"검사 {len(targets)}개 파일",
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
    """모든 공개 path operation 이 async 이고 요청 경로에서 동기 I/O 를 하지 않는지.

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
        "path operation async + 동기 I/O 부재",
        not problems and total > 0,
        f"동기 def={sync_operations} 블로킹호출={blocking}" if problems else f"검사 {total}건",
    )


# 이 계열 결함은 lifespan 바깥(취소·프로세스 종료·신호 처리)에 살아 다른 테스트로는 보이지 않는다.
# 그래서 "있는지" 를 기계가 본다 — 느리다는 이유로 조용히 지워지면 그 순간 눈이 없어진다.
PROCESS_LEVEL_TESTS = (
    "tests/core/test_resources.py::test_manager_cancellation_still_runs_remaining_cleanup",
    "tests/utils/test_logs.py::test_signal_shutdown_still_drains_the_log_listener",
)


def check_process_level_tests_collected() -> None:
    """취소·프로세스 종료 테스트가 실재하고 **수집되는지**.

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
        "취소·프로세스 종료 테스트 실재",
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
    print("품질 게이트")
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
    # 초록불 아래에서 조용히 쌓인다 — 실제로 19건이 그렇게 쌓였다.
    run_tool(
        "의존성 취약점 0건",
        ["-m", "pip_audit", "--strict", "--progress-spinner", "off"],
        tail_lines=30,
    )
    check_layering()
    check_public_api_unchanged()
    check_no_table_drop_in_app()
    check_no_empty_python_files()
    check_async_path_operations()
    check_process_level_tests_collected()

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
