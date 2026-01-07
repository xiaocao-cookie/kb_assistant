from celery import Celery
from app.config import settings


celery_app = Celery("kb_assistant", broker=settings.celery_broker_url)


# _existing = tuple(celery_app.conf.get("imports") or ())
#
# if "app.tasks.audio_tasks" not in _existing:
#     celery_app.conf.imports = _existing + ("app.tasks.audio_tasks", )

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    timezone="UTC"
)

celery_app.autodiscover_tasks(["app.tasks"])