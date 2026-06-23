def test_celery_app_configured():
    from app.core.celery.app import celery_app
    assert celery_app.conf.broker_url.startswith("redis://")
    # 태스크 모듈이 명시적으로 include 됨 (autodiscover 미사용)
    assert "app.domains.home.worker.tasks" in celery_app.conf.include
