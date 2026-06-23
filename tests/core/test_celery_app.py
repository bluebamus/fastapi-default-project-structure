def test_celery_app_configured():
    from app.core.celery.app import celery_app
    assert celery_app.conf.broker_url.startswith("redis://")
    # home package is among autodiscover packages
    assert any("home" in p for p in celery_app.conf["__autodiscover_packages__"])
