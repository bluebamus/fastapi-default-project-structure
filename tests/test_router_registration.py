"""라우터 등록 누락 탐지 (표준 include_router 배선 기준).

`app/features/` 의 각 기능 패키지가 공개하는 ``router`` 가 `main.app` 에 실제로
마운트됐는지 대조한다. `main.py` 에서 `include_router` 한 줄을 빠뜨리면 그 기능의
라우트가 조용히 사라지는데(늦게 발견되는 회귀), 이 테스트가 즉시 잡는다.

또한 `models/models.py` 를 가진 기능이 빠짐없이 `Base.metadata` 에 등록되는지도
확인한다 — 누락 시 마이그레이션이 비거나 테이블이 안 생긴다.
"""

import importlib
import pkgutil

import app.features
from app.core.db.models_registry import import_all_models, iter_model_modules
from app.core.db.session import Base


def _modules_with_router() -> set[str]:
    """``router`` 를 공개하는 기능 패키지 이름 집합."""
    names: set[str] = set()
    for info in pkgutil.iter_modules(app.features.__path__):
        if not info.ispkg:
            continue
        module = importlib.import_module(f"app.features.{info.name}")
        if getattr(module, "router", None) is not None:
            names.add(info.name)
    return names


def _mounted_paths() -> set[str]:
    from main import app

    return set(app.openapi()["paths"].keys())


def test_every_feature_router_is_mounted():
    """router 를 공개하는 기능은 모두 main.app 에 마운트돼 있어야 한다.

    각 기능은 ``/api/v1/<name>/...`` 로 마운트되므로(기능명 = URL 세그먼트),
    마운트된 경로 중 ``/<name>/`` 를 포함하는 것이 있는지로 누락을 잡는다.
    """
    mounted = _mounted_paths()
    missing = {
        name for name in _modules_with_router() if not any(f"/{name}/" in path for path in mounted)
    }
    assert not missing, (
        f"main.py 에서 include_router 를 빠뜨린 기능: {sorted(missing)}. "
        "app.include_router(<name>.router, prefix='/api') 를 추가할 것."
    )


def test_every_model_is_in_metadata():
    """models/models.py 를 가진 기능은 빠짐없이 Base.metadata 에 등록돼야 한다."""
    import pathlib

    import_all_models()

    modules_dir = pathlib.Path(app.features.__path__[0])
    with_models = {
        info.name
        for info in pkgutil.iter_modules(app.features.__path__)
        if info.ispkg and (modules_dir / info.name / "models" / "models.py").is_file()
    }
    registered = {dotted.split(".")[2] for dotted in iter_model_modules()}

    # 모델 없는 기능(auth 등)은 정상 제외 — "파일은 있는데 새는" 경우만 잡는다.
    assert (
        with_models - registered == set()
    ), f"models.py 가 있는데 등록되지 않은 기능: {sorted(with_models - registered)}"
    assert Base.metadata.tables, "Base.metadata 가 비어 있다 — 마이그레이션이 빈 채로 생성된다"
