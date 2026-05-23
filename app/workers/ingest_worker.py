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
        "workers.ingest_worker.ingest_workspace_task": {"queue": "workspace_ingestion"},
        "workers.ingest_worker.ingest_enterprise_task": {"queue": "enterprise_ingestion"},
        "workers.ingest_worker.ingest_confluence_task": {"queue": "enterprise_ingestion"},
    },
)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=5, queue="workspace_ingestion")
def ingest_workspace_task(self, file_path: str, **kwargs) -> dict:
    try:
        result = asyncio.run(_run_workspace_ingest(file_path=file_path, **kwargs))
        _safe_remove(file_path)
        return result
    except self.MaxRetriesExceededError:
        _safe_remove(file_path)
        raise
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5, queue="enterprise_ingestion")
def ingest_enterprise_task(self, file_path: str, file_name: str) -> dict:
    try:
        result = asyncio.run(
            _run_enterprise_ingest(file_path=file_path, file_name=file_name)
        )
        return result
    except self.MaxRetriesExceededError:
        raise
    except Exception as exc:
        raise self.retry(exc=exc)
    finally:
        _safe_remove(file_path)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, queue="enterprise_ingestion")
def ingest_confluence_task(self, page_id: str) -> dict:
    try:
        data = {"page": {"id": page_id}}
        result = asyncio.run(_run_confluence_ingest(data))
        return result
    except self.MaxRetriesExceededError:
        raise
    except Exception as exc:
        raise self.retry(exc=exc)


def _safe_remove(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"[Worker] Cleaned up {path}")
    except Exception as e:
        logger.warning(f"[Worker] Failed to clean up {path}: {e}")


async def _run_workspace_ingest(file_path: str, **kwargs) -> dict:
    async with aiofiles.open(file_path, "rb") as f:
        file_content = await f.read()
    return await workspace_ingestion_service.ingest(
        file_content=file_content, **kwargs
    )


async def _run_confluence_ingest(data: dict) -> dict:
    from service import document_processor

    page_id = str(data.get("page", {}).get("id", ""))
    await document_processor.extract(data, "CONFLUENCE")
    return {"status": "success", "page_id": page_id}


async def _run_enterprise_ingest(file_path: str, file_name: str) -> dict:
    from service import document_processor

    doc_data = {
        "file_path": file_path,
        "filename": file_name,
    }
    await document_processor.extract(doc_data, "FILE")
    return {"status": "success", "file_name": file_name}