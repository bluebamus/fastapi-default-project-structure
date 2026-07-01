"""Test that importing each domain app's models populates Base.metadata.

This guards the env.py / create_db_tables approach: if the explicit model
imports fail, autogenerate would produce an empty migration and
create_db_tables would create no tables.
"""


def test_domain_models_populate_metadata():
    # env.py / create_db_tables 와 동일한 명시적 import 경로
    import app.domains.blog.models.models  # noqa: F401
    import app.domains.home.models.models  # noqa: F401
    import app.domains.reply.models.models  # noqa: F401
    import app.domains.sns.models.models  # noqa: F401
    import app.domains.user.models.models  # noqa: F401
    from app.core.db.session import Base

    tables = Base.metadata.tables
    assert "user_access_logs" in tables
    # 5개 도메인 앱의 모델이 모두 메타데이터에 등록되어야 한다.
    assert len(tables) >= 5
