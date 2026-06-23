from app.domains.home.config import HomeConfig


def test_home_config_exposes_router_and_admin():
    cfg = HomeConfig()
    assert cfg.name == "home"
    assert cfg.package == "app.domains.home"
    assert cfg.router() is not None
    assert len(cfg.admin_views()) == 1
