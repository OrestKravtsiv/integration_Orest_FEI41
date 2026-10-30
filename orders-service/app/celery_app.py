import os

from celery import Celery

celery_app = Celery(
    "orders",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    include=["app.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)
