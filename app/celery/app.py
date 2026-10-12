"""중앙 Celery 앱.

모든 도메인의 백그라운드 태스크는 app/celery/tasks.py 에 중앙 집중한다.
앱별 worker/ 디렉토리는 제거되었으며 이 패키지(app/celery)가 대체한다.
"""

from celery import Celery

# import 만으로 worker_process_init/shutdown 시그널이 등록된다.
# worker 는 이 모듈을 진입점으로 로드하므로 여기가 등록의 유일한 지점이다(AR-010).
from app.celery import lifecycle  # noqa: F401 - 시그널 등록 부작용이 목적
from config import redis_settings, timezone_settings

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
    # 내부 시각(ETA·만료·결과 메타)은 UTC 로 다룬다 — DB 저장 시각과 같은 기준(service-hardening
    # ADR-010). ``timezone`` 은 beat 의 crontab 을 해석할 로컬 시간대다(설정 TIME_ZONE 일원화).
    timezone=timezone_settings.TIME_ZONE,
    enable_utc=True,
    beat_schedule={},
)
