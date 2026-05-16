from __future__ import annotations

import asyncio
import os
import logging
import aiofiles

logger = logging.getLogger(__name__)

from celery import Celery
from service.workspace_ingestion import workspace_ingestion_service

REDIS_BROKER_URL = os.getenv("REDIS_BROKER_URL", "redis://localhost:6379/0")
REDIS_BACKEND_URL = os.getenv("REDIS_BACKEND_URL", "redis://localhost:6379/1")

celery_app = Celery(
    "ingest",
    broker=REDIS_BROKER_URL,
    backend=REDIS_BACKEND_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_expires=3600,             
    task_acks_late=True,             
    worker_prefetch_multiplier=1,    
    worker_max_tasks_per_child=100, 
    task_routes={
        "workers.ingest_worker.ingest_file_task": {"queue": "ingestion"},
    },
)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5, queue="ingestion")
def ingest_file_task(self, file_path: str, **kwargs) -> dict:
    try:
        result = asyncio.run(_run_ingest(file_path=file_path, **kwargs))
        _safe_remove(file_path)
        return result
    except self.MaxRetriesExceededError:
        _safe_remove(file_path)
        raise
    except Exception as exc:
        raise self.retry(exc=exc)


def _safe_remove(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        logger.warning(f"[Worker] Failed to clean up {path}: {e}")


async def _run_ingest(file_path: str, **kwargs) -> dict:
    async with aiofiles.open(file_path, "rb") as f:
        file_content = await f.read()
    return await workspace_ingestion_service.ingest(
        file_content=file_content, **kwargs
    )