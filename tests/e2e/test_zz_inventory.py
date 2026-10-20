"""W3 — 인벤토리 대조: 실제 앱에서 뽑은 대상마다 그것을 실행한 테스트(또는 N/A 사유)가 있어야 한다.

이 파일은 스위트의 **끝**에서 돈다(파일 이름 순서). 앞의 테스트가 ``cover(...)`` 로 장부에 적은 칸과
여기서 만든 기대 목록을 맞춘다 — 빈 칸이 있거나 기대 목록에 없는 칸(오타)이 있으면 실패한다.
단독으로(-k 등으로 일부만) 돌리면 당연히 빈 칸이 생겨 실패한다.

결과 표는 실행 디렉터리의 ``inventory.md`` 에 남는다(CI artifact).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.e2e.stack import ROOT
from tests.e2e.support import LEDGER, NOTES

pytestmark = pytest.mark.e2e

API_CELLS = ("ok", "validation", "unauth", "forbidden", "notfound", "method", "policy")
ADMIN_CELLS = (
    "list",
    "detail",
    "create",
    "edit",
    "delete",
    "bulk-delete",
    "export",
    "filter-on",
    "filter-on_or_after",
    "filter-before",
    "filter-between",
)
# 계획서 §1.2·§3 L4~L6 의 요청 종류 — 앱에서 뽑을 수 없는 "행위" 목록이라 여기 적는다.
STATIC = {
    ("admin-auth", "login"): ("success", "wrong-password", "csrf-missing", "rate-limit"),
    ("admin-auth", "logout"): ("get-405", "post"),
    ("admin-auth", "csrf"): ("create", "edit", "delete", "logout", "body-cap-413"),
    ("admin-auth", "session"): (
        "idle-expiry",
        "absolute-expiry",
        "revoke-on-deactivate",
        "revoke-on-demote",
        "revoke-on-delete",
    ),
    ("admin-auth", "admin-disabled"): ("404",),
    ("fault", "redis"): ("stop-start",),
    ("fault", "worker"): ("stop-start",),
    ("fault", "replica"): ("stop-start",),
    ("fault", "primary"): ("stop-start",),
    ("ops", "alembic"): ("round-trip",),
    ("ops", "create_superuser"): ("create-promote-reject",),
    ("ops", "startup-refusal"): (
        "access-policy",
        "legacy-ADMIN",
        "ADMIN_SESSION_*",
        "redis-min-version",
    ),
    ("logging", "format"): ("all-run-paths",),
    ("logging", "app-levels"): ("LOG_APP_LEVELS",),
    ("logging", "files"): ("per-process", "rotation-retention"),
    ("redis", "celery-broker-backend"): ("used",),
}
_KEY = re.compile(r'f?"((?:admin|auth):[\w\-:]*)')
_URL_NAME = re.compile(r'url_for\(\s*"admin:')


def redis_prefixes() -> set[str]:
    """앱 소스의 Redis 키 접두어 — ``admin:``·``auth:`` 로 시작하는 키 문자열(라우트 이름 ``url_for`` 제외)."""
    found = set()
    for path in (ROOT / "app").rglob("*.py"):
        if "tests" in path.parts:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if _URL_NAME.search(line) or line.lstrip().startswith("#"):
                continue
            for literal in _KEY.findall(line):
                parts = [p for p in literal.split(":") if p]
                found.add(":".join(parts[:3] if parts[1] == "rl" else parts[:2]) + ":")
    return found


def expected() -> set[tuple[str, str, str]]:
    from app.celery.app import celery_app
    from app.core.db.models_registry import iter_task_modules
    from app.core.security.access import AccessPolicyGuard
    from app.features.admin import ADMIN_VIEWS
    from main import app

    for module in iter_task_modules():
        __import__(module)
    keys = {
        ("api", label, cell) for label, _ in AccessPolicyGuard().routes(app) for cell in API_CELLS
    }
    keys |= {("admin", view.identity, cell) for view in ADMIN_VIEWS for cell in ADMIN_CELLS}
    keys |= {
        ("celery", name, "worker") for name in celery_app.tasks if not name.startswith("celery.")
    }
    keys |= {("celery", f"beat:{name}", "schedule") for name in celery_app.conf.beat_schedule}
    keys |= {("redis", prefix, "used") for prefix in redis_prefixes()}
    keys |= {(kind, item, cell) for (kind, item), cells in STATIC.items() for cell in cells}
    return keys


def _write_table(stack, want: set) -> Path:
    rows = ["| 종류 | 항목 | 칸 | 근거 |", "|---|---|---|---|"]
    for key in sorted(want):
        evidence = "; ".join(sorted(set(LEDGER.get(key, [])))) or "**빈 칸**"
        rows.append(f"| {key[0]} | `{key[1]}` | {key[2]} | {evidence} |")
    rows += ["", "## 기록(판정 아님)", ""] + [f"- {k}: {v}" for k, v in sorted(NOTES.items())]
    path = stack.run_dir / "inventory.md"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_redis_prefix_extraction_finds_the_known_keys():
    assert redis_prefixes() == {
        "admin:sess:",
        "admin:user_sessions:",
        "admin:rl:login:",
        "auth:rt:",
        "auth:fam:",
        "auth:user:",
        "auth:rl:login:",
        "auth:rl:register:",
    }


def test_every_inventory_cell_is_filled(stack):
    want = expected()
    table = _write_table(stack, want)
    empty = sorted(k for k in want if not LEDGER.get(k))
    unknown = sorted(k for k in LEDGER if k not in want)
    assert not empty, f"빈 칸 {len(empty)}개 (표: {table}):\n" + "\n".join(map(str, empty[:40]))
    assert not unknown, f"인벤토리에 없는 칸을 적었다(오타?): {unknown}"
