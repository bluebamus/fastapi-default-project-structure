"""중앙 Celery 앱.

태스크는 각 기능의 ``app/features/<name>/tasks.py`` 에 둔다(service-hardening ADR-012).
``include`` 는 모델 등록과 같은 기능 패키지 탐색(``app/core/db/models_registry.py``)이 만든다 —
이 패키지(app/celery)는 기능을 import 하지 않으므로, 기능을 지우면 그 태스크도 include 에서
함께 빠지고 워커는 깨지지 않는다.
"""

from celery import Celery

# import 만으로 worker_process_init/shutdown 시그널이 등록된다.
# worker 는 이 모듈을 진입점으로 로드하므로 여기가 등록의 유일한 지점이다(AR-010).
from app.celery import lifecycle  # noqa: F401 - 시그널 등록 부작용이 목적
from app.core.db.models_registry import import_all_models, iter_task_modules
from config import redis_settings, timezone_settings

# 워커 기동 시 모든 기능 모델을 등록한다 — 태스크가 쓰는 모델의 relationship 이 다른 기능 모델을
# 문자열로 가리켜도 mapper 구성이 실패하지 않게. API 의 lifespan 과 같은 단일 지점을 쓴다.
import_all_models()

celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
    include=iter_task_modules(),
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
