from app.core.registry import AppConfig


class DummyConfig(AppConfig):
    name = "dummy"


def test_appconfig_defaults():
    cfg = DummyConfig()
    assert cfg.name == "dummy"
    assert cfg.category == "domain"
    assert cfg.prefix == "/api"
    assert cfg.enabled is True
    assert cfg.order == 100
    assert cfg.router() is None
    assert cfg.admin_views() == []
    assert cfg.beat_schedule() == {}
