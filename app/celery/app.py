"""중앙 Celery 앱.

모든 도메인의 백그라운드 태스크는 app/celery/tasks.py 에 중앙 집중한다.
앱별 worker/ 디렉토리는 제거되었으며 이 패키지(app/celery)가 대체한다.
"""

from celery import Celery

from config import redis_settings

celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
    include=["app.celery.tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=False,
    beat_schedule={},
)
