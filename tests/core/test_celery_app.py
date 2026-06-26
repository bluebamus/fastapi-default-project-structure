def test_celery_app_configured():
    from app.core.celery.app import celery_app
    assert celery_app.conf.broker_url.startswith("redis://")
    # 태스크는 autodiscover_tasks 로 등록됨 — home 패키지가 발견 목록에 포함
    assert any("home" in p for p in celery_app.conf["__autodiscover_packages__"])
