from celery import Celery

from app.config import settings

celery_app = Celery("fintrack", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC")

from app.workers.beat_schedule import BEAT_SCHEDULE  # noqa: E402
from app.workers import tasks  # noqa: F401,E402  (imports every task module so they register with celery_app)

celery_app.conf.beat_schedule = BEAT_SCHEDULE
