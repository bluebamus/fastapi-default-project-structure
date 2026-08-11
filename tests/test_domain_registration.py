"""도메인 등록 누락 탐지 (계획서 P2-3).

`app/features/` 디렉터리를 진실의 원천으로 삼아, 실제로 존재하는 도메인이 실행
경로에 모두 연결되어 있는지 대조한다. 스캐폴딩 후 등록을 잊으면 라우터가 마운트
되지 않거나 테이블이 생성되지 않는데, 둘 다 조용히 실패해서 늦게 발견된다.

의도적으로 제외할 도메인은 아래 allowlist 에 이유와 함께 명시한다. 조용한 누락과
의도적 제외를 구분하기 위한 장치이며, allowlist 자체도 낡으면 실패하도록 검증한다.
"""

import pathlib
import pkgutil

import app.features
from app.core.db.models_registry import iter_model_modules
from app.core.db.session import Base
from main import APPS

# 라우터를 마운트하지 않는 도메인이 생기면 여기에 이유와 함께 적는다.
_UNREGISTERED_BY_DESIGN: dict[str, str] = {}

# 모델이 없는 도메인(auth 등)은 allowlist 가 필요 없다. models_registry 가 파일
# 존재 여부로 판별하므로, 아래 테스트는 "models.py 가 있는데 빠졌는가"만 본다.


_DOMAINS_DIR = pathlib.Path(app.features.__path__[0])


def _discovered_domains() -> set[str]:
    return {info.name for info in pkgutil.iter_modules(app.features.__path__) if info.ispkg}


def _registered_domains() -> set[str]:
    return {module.__name__.rsplit(".", 1)[-1] for module in APPS}


def test_every_domain_is_registered_in_apps():
    """디렉터리에 있는 도메인은 main.py 의 APPS 에 모두 있어야 한다."""
    missing = _discovered_domains() - _registered_domains() - set(_UNREGISTERED_BY_DESIGN)

    assert not missing, (
        f"main.py 의 APPS 에 등록되지 않은 도메인: {sorted(missing)}. "
        "python -m scripts.new_app <name> --register 로 등록하거나, "
        "의도된 제외라면 _UNREGISTERED_BY_DESIGN 에 이유와 함께 추가할 것."
    )


def test_apps_has_no_phantom_entries():
    """APPS 에는 있는데 디렉터리에 없는 도메인이 없어야 한다(삭제 후 잔존)."""
    phantom = _registered_domains() - _discovered_domains()

    assert not phantom, f"디렉터리에 없는 도메인이 APPS 에 남아 있다: {sorted(phantom)}"


def test_every_domain_with_models_is_in_metadata():
    """models/models.py 를 가진 도메인은 빠짐없이 등록 대상이어야 한다.

    모델이 없는 도메인은 정상이므로 대상에서 빠져도 실패시키지 않는다. 잡으려는
    것은 "파일은 있는데 등록에서 새는" 경우뿐이다.
    """
    from app.core.db.models_registry import import_all_models

    import_all_models()

    registered = {dotted.split(".")[2] for dotted in iter_model_modules()}
    on_disk = {
        name
        for name in _discovered_domains()
        if (_DOMAINS_DIR / name / "models" / "models.py").is_file()
    }

    assert (
        on_disk - registered == set()
    ), f"models.py 가 있는데 등록되지 않은 도메인: {sorted(on_disk - registered)}"
    assert Base.metadata.tables, "Base.metadata 가 비어 있다 — 마이그레이션이 빈 채로 생성된다"


def test_allowlists_are_not_stale():
    """사라진 도메인이 allowlist 에 남아 있으면 실패한다.

    allowlist 는 예외를 눈에 보이게 하려고 두는 것이라, 스스로 낡으면 의미가 없다.
    """
    discovered = _discovered_domains()

    stale = set(_UNREGISTERED_BY_DESIGN) - discovered

    assert not stale, f"존재하지 않는 도메인이 allowlist 에 남음: {sorted(stale)}"
