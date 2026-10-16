"""
tasks/celery_app.py
===================
Celery application factory.

3 queues, matching the 3 scraper types:
  - cases      → court pipeline (Selenium, ThreadPool)
  - deed        → deed search (Selenium or HTTP)
  - obituary    → obituary HTTP search

Workers are started separately per queue so concurrency can be tuned
independently — e.g. 8 court workers, 4 deed workers, 8 obituary workers.

Start commands (run each in a separate terminal):
    celery -A tasks.celery_app worker -Q cases     --concurrency=8 --pool=threads -n court@%h
    celery -A tasks.celery_app worker -Q deed      --concurrency=4 --pool=threads -n deed@%h
    celery -A tasks.celery_app worker -Q obituary  --concurrency=8 --pool=prefork -n obituary@%h
    celery -A tasks.celery_app flower --port=5555
"""
import sys
from pathlib import Path

# Ensure project root directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from celery import Celery

from config import settings

celery_app = Celery(
    "court_scraper",
    include=[
        "tasks.case_tasks",
        "tasks.deed_tasks",
        "tasks.obituary_tasks",
    ],
)

celery_app.conf.update(
    # ── Broker / Backend ────────────────────────────────────────────────────
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,

    # ── Serialisation ────────────────────────────────────────────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # ── Reliability ──────────────────────────────────────────────────────────
    task_acks_late=True,            # re-queue task if worker dies mid-flight
    worker_prefetch_multiplier=1,   # don't pre-fetch; fairness for long tasks
    task_track_started=True,
    task_reject_on_worker_lost=True,

    # ── Routing ─────────────────────────────────────────────────────────────
    task_routes={
        "tasks.case_tasks.run_case_pipeline":      {"queue": "cases"},
        "tasks.deed_tasks.run_deed_job_task":       {"queue": "deed"},
        "tasks.obituary_tasks.run_obituary_task":   {"queue": "obituary"},
    },

    # ── Result TTL ───────────────────────────────────────────────────────────
    result_expires=3600,  # auto-clean results after 1 hour
)
