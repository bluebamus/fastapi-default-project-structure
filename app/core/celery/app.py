from celery import Celery

from app.core.registry import AppRegistry
from config import redis_settings

# 태스크는 AppRegistry 자동발견으로 등록한다.
# autodiscover_tasks 가 각 도메인 패키지의 worker/tasks.py 를 import 하여 태스크를 등록한다.
registry = AppRegistry()
registry.discover()

celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=False,
    beat_schedule=registry.merged_beat_schedule(),
)
_packages = registry.celery_packages()
celery_app.conf["__autodiscover_packages__"] = _packages
celery_app.autodiscover_tasks(_packages, related_name="worker.tasks")
