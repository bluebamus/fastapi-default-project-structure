"""Test: home.aggregate_access_stats task registration (central app/celery/tasks.py)."""


def test_aggregate_task_registered():
    from app.celery import tasks  # noqa: F401  (ensures central task module is imported)
    from app.celery.app import celery_app

    assert "home.aggregate_access_stats" in celery_app.tasks
