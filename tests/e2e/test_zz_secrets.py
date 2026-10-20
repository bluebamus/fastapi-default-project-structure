"""L6.4 — 실행 로그 전체에서 비밀값 원문 0건.

대상 값: 실행마다 만든 DB(root·앱·복제) 비밀번호, JWT 서명 키 두 개, 세션 키, 슈퍼유저·테스트 사용자
비밀번호, 테스트가 발급받은 access·refresh 토큰. 대상 파일: 앱(uvicorn)·worker·beat·도구(alembic·
create_superuser) 출력과 프로세스별 로그 파일(app·error·celery·회전 파일) 전부.

마지막 테스트다 — 자식 프로세스를 먼저 멈춰 큐에 남은 줄까지 파일로 내려보낸 뒤 읽는다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_no_secret_appears_in_any_run_log(stack):
    stack.stop_app()
    stack.stop_worker()
    files = [p for p in stack.run_dir.rglob("*") if p.is_file() and ".log" in p.name]
    assert len(files) > 10, files
    secrets = {s for s in stack.secrets if len(s) >= 16}
    assert len(secrets) >= 7
    hits = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        hits += [path.name for s in secrets if s in text]  # 값은 출력하지 않는다
    assert not hits, f"비밀값 원문이 로그에 있다: {hits}"
    # DSN 은 가려진 꼴로만 나온다. 이 줄은 import 중에 찍히지만 콘솔과 프로세스 파일(app.log) 모두에
    # 남는다 — 파일 핸들러가 설정 로드 직후 붙는다(F-003, ADR-011).
    masked = "mysql+aiomysql://***:***@127.0.0.1:13321/***"
    console = next(stack.run_dir.glob("*-app.log")).read_text(encoding="utf-8")
    assert masked in console
    assert masked in (stack.app_log_dir / "app.log").read_text(encoding="utf-8")
