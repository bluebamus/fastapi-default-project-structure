from celery import Celery

from app.apps import BEAT_SCHEDULE, CELERY_TASK_MODULES
from config import redis_settings

# 태스크 모듈은 app/apps.py 의 CELERY_TASK_MODULES 에 명시적으로 등록한다.
# include= 로 전달하면 Celery 가 해당 모듈을 import 하여 태스크를 등록한다(autodiscover 미사용).
celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
    include=CELERY_TASK_MODULES,
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=False,
    beat_schedule=BEAT_SCHEDULE,
)
