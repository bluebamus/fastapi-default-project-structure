def test_celery_app_configured():
    from app.celery.app import celery_app

    assert celery_app.conf.broker_url.startswith("redis://")
    # 태스크는 중앙 app/celery/tasks.py 에 include 로 등록된다 (앱별 worker 제거).
    assert "app.celery.tasks" in celery_app.conf.include
