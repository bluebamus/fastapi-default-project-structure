"""Test that importing each domain app's models populates Base.metadata.

This guards the env.py / create_db_tables approach: if the explicit model
imports fail, autogenerate would produce an empty migration and
create_db_tables would create no tables.

import 목록은 models_registry 가 디렉터리에서 판별한다(SSOT). 여기서도 같은
경로를 쓰므로, 목록이 세 파일에 복제되어 어긋나던 문제가 재발하지 않는다.
"""

from app.core.db.models_registry import import_all_models, iter_model_modules


def test_domain_models_populate_metadata():
    # env.py / create_db_tables 와 동일한 import 경로
    from app.core.db.session import Base

    import_all_models()

    tables = Base.metadata.tables
    assert "user_access_logs" in tables
    # 5개 도메인 앱의 모델이 모두 메타데이터에 등록되어야 한다.
    assert len(tables) >= 5


def test_registry_discovers_expected_domains():
    """디렉터리 판별이 실제 도메인과 맞는지 고정한다.

    모델이 없는 도메인(auth)은 목록에 없어야 한다 — 없다고 실패하면 안 된다.
    """
    modules = iter_model_modules()

    assert "app.features.blog.models.models" in modules
    assert "app.features.user.models.models" in modules
    assert (
        "app.features.auth.models.models" not in modules
    ), "auth 는 모델이 없다. 모델 없는 도메인을 등록 대상으로 잡으면 import 에러가 난다"
