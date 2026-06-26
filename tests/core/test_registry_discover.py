from app.core.registry import AppRegistry


def test_discover_reads_installed_apps_in_order(monkeypatch):
    """수동 등록: discover 는 config.INSTALLED_APPS 를 목록 순서 그대로 읽는다(정렬 안 함)."""
    import config

    monkeypatch.setattr(config, "INSTALLED_APPS", ["beta", "alpha"])
    reg = AppRegistry()
    apps = reg.discover(package="tests.core._fakeapps")
    assert [a.name for a in apps] == ["beta", "alpha"]   # 목록 순서 보존
    assert reg.enabled_apps == apps
    assert all(a.package.startswith("tests.core._fakeapps.") for a in apps)


def test_discover_uses_real_installed_apps():
    """실제 config.INSTALLED_APPS 에 등록된 도메인 앱들이 발견된다."""
    reg = AppRegistry()
    names = [a.name for a in reg.discover()]
    assert "home" in names
    assert "blog" in names
    assert names[0] == "home"        # INSTALLED_APPS 의 첫 항목(명시적 순서)
