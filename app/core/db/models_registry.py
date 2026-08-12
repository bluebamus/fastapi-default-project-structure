"""기능 모델 import 단일 지점 (SSOT).

Alembic autogenerate 와 DEBUG 모드 테이블 생성은 둘 다 `Base.metadata` 가 채워져
있어야 동작한다. 그러려면 각 기능의 models 모듈이 import 되어 있어야 하는데,
같은 import 목록을 여러 파일에 복제하면 새 기능 추가 시 한쪽만 고쳐 조용히
어긋난다. 증상은 나중에 "마이그레이션이 비어 있음" 또는 "테이블이 안 생김" 으로
나타나서 원인을 찾기 어렵다.

그래서 목록 대신 **디렉터리 구조를 진실의 원천**으로 삼는다. `app/features/<name>/
models/models.py` 가 있으면 등록 대상이고, 없으면(예: 모델이 없는 `auth`) 건너뛴다.
새 기능을 추가할 때 모델 등록 때문에 손댈 곳이 없다.
"""

import importlib
import importlib.util

_MODELS_SUFFIX = "models.models"


def iter_model_modules() -> list[str]:
    """models/models.py 를 가진 기능의 모듈 경로를 정렬해 돌려준다.

    import 는 하지 않는다 — 목록만 필요한 검사(테스트 등)가 부작용 없이 쓰도록.
    """
    import pkgutil

    import app.features

    modules: list[str] = []
    for info in pkgutil.iter_modules(app.features.__path__):
        if not info.ispkg:
            continue
        dotted = f"app.features.{info.name}.{_MODELS_SUFFIX}"
        try:
            exists = importlib.util.find_spec(dotted) is not None
        except ModuleNotFoundError:
            # models 패키지 자체가 없는 기능 — 정상이다(auth 처럼 모델이 없는 경우).
            exists = False
        if exists:
            modules.append(dotted)
    return sorted(modules)


def import_all_models() -> list[str]:
    """모든 기능 모델 모듈을 import 해 `Base.metadata` 를 채운다.

    Returns:
        실제로 import 한 모듈 경로 목록(정렬됨). 로깅과 검증에 쓴다.
    """
    modules = iter_model_modules()
    for dotted in modules:
        importlib.import_module(dotted)
    return modules
