import logging

from celery import Celery
from app.config import settings


celery_app = Celery(
    "kb_assistant",
    broker=settings.celery_broker_url
)


logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("faster_whisper").setLevel(logging.WARNING)


celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    timezone="UTC"
)

celery_app.autodiscover_tasks(["app.tasks"], related_name="audio_tasks")