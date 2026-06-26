from app.core.registry import AppRegistry


def test_discover_finds_direct_subpackages_alphabetically():
    """컨벤션 스캔: package 직계 하위 서브패키지를 알파벳순으로 발견한다."""
    reg = AppRegistry()
    apps = reg.discover(package="tests.core._fakeapps")
    names = [a.name for a in apps]
    assert names == ["alpha", "beta"]          # 알파벳 정렬(언더스코어 디렉터리 제외)
    assert reg.enabled_apps == apps
    assert all(a.package.startswith("tests.core._fakeapps.") for a in apps)
