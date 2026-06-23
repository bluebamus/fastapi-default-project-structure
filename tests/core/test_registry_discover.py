from app.core.registry import AppRegistry


def test_discover_is_recursive_and_ordered():
    reg = AppRegistry()
    apps = reg.discover(package="tests.core._fakeapps")
    names = [a.name for a in apps]
    assert names == ["alpha", "beta"]          # sorted by order, recursion found beta/sub
    assert reg.enabled_apps == apps
