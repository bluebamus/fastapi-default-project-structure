"""
Test: home.aggregate_access_stats task registration.
"""


def test_aggregate_task_registered():
    from app.core.celery.app import celery_app
    from app.domains.home.worker import tasks  # noqa: F401

    assert "home.aggregate_access_stats" in celery_app.tasks
