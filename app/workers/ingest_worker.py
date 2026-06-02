from __future__ import annotations

import asyncio
import os
import logging

import random

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

from celery import Celery
from workers.chunk_io import safe_remove
from workers.workspace.workspace_chunk import run_workspace_chunk
from workers.workspace.workspace_embed import run_workspace_embed
from workers.enterprise.enterprise_chunk import run_enterprise_chunk
from workers.enterprise.enterprise_embed import run_enterprise_embed
from workers.job_status import update_job, fail_job,increment_upserted

REDIS_BROKER_URL  = os.getenv("REDIS_BROKER_URL",  "redis://localhost:6379/0")
REDIS_BACKEND_URL = os.getenv("REDIS_BACKEND_URL", "redis://localhost:6379/1")
WORKER_MAX_TASKS_PER_CHILD = int(os.getenv("WORKER_MAX_TASKS_PER_CHILD", 200))
REDIS_TASK_RESULT_TTL_SECONDS = int(os.getenv("REDIS_TASK_RESULT_TTL_SECONDS", 3600))
WORKER_PREFETCH_MULTIPLIER = int(os.getenv("WORKER_PREFETCH_MULTIPLIER", 1))

CELERY_MAX_RETRIES = int(os.getenv("CELERY_MAX_RETRIES", 5))
CELERY_BASE_DELAY_SECONDS = int(os.getenv("CELERY_BASE_DELAY_SECONDS", 5))
CELERY_MAX_DELAY_SECONDS = int(os.getenv("CELERY_MAX_DELAY_SECONDS", 300))

EMBED_RATE_LIMIT = os.getenv("EMBED_RATE_LIMIT", "120/m")

celery_app = Celery(
    "ingest",
    broker=REDIS_BROKER_URL,
    backend=REDIS_BACKEND_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_expires=REDIS_TASK_RESULT_TTL_SECONDS, #redis stores task results for 1 hour not the tasks
    task_acks_late=True,
    worker_prefetch_multiplier=WORKER_PREFETCH_MULTIPLIER,
    worker_max_tasks_per_child=WORKER_MAX_TASKS_PER_CHILD,
    task_routes={
        "workers.ingest_worker.chunk_workspace_task":    {"queue": "workspace_chunk"},
        "workers.ingest_worker.embed_workspace_task":    {"queue": "workspace_embed"},
        "workers.ingest_worker.dbwrite_workspace_task":  {"queue": "workspace_dbwrite"},
        "workers.ingest_worker.chunk_enterprise_task":   {"queue": "enterprise_chunk"},
        "workers.ingest_worker.embed_enterprise_task":   {"queue": "enterprise_embed"},
        "workers.ingest_worker.dbwrite_enterprise_task": {"queue": "enterprise_dbwrite"},
        "workers.ingest_worker.ingest_confluence_task":  {"queue": "enterprise_chunk"},
    },
    task_annotations={
        "workers.ingest_worker.embed_workspace_task":  {"rate_limit": EMBED_RATE_LIMIT},
        "workers.ingest_worker.embed_enterprise_task": {"rate_limit": EMBED_RATE_LIMIT},
    },
)


def _backoff(self, base: int = CELERY_BASE_DELAY_SECONDS, max_delay: int = CELERY_MAX_DELAY_SECONDS) -> float:
    """Exponential backoff with full jitter."""
    exp = min(base * (2 ** self.request.retries), max_delay)
    return random.uniform(0, exp)


@celery_app.task(
    bind=True, max_retries=CELERY_MAX_RETRIES,
    queue="workspace_chunk",
    name="workers.ingest_worker.chunk_workspace_task",
)
def chunk_workspace_task(
    self,
    job_id: str,
    file_path: str,
    file_name: str,
    file_extension: str,
    path: str,
    path_id: str,
    workspace_id: str,
    workspace_path: str,
    content_id: str,
    raw_user_header: str,
) -> dict:
    try:
        return asyncio.run(
            run_workspace_chunk(
                job_id=job_id,
                file_path=file_path,
                file_name=file_name,
                file_extension=file_extension,
                path=path,
                path_id=path_id,
                workspace_id=workspace_id,
                workspace_path=workspace_path,
                content_id=content_id,
                raw_user_header=raw_user_header,
            )
        )
    except self.MaxRetriesExceededError:
        safe_remove(file_path)
        asyncio.run(fail_job(job_id, "Max retries exceeded in chunk stage"))
        raise
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_backoff(self))



@celery_app.task(
    bind=True, max_retries=CELERY_MAX_RETRIES,
    queue="workspace_embed",
    name="workers.ingest_worker.embed_workspace_task",
)
def embed_workspace_task(
    self,
    job_id: str,
    jsonl_path: str,
    dense_type: str,
    sparse_type: str,
    upsert_meta: dict,
) -> dict:
    try:
        return asyncio.run(
            run_workspace_embed(
                job_id=job_id,
                jsonl_path=jsonl_path,
                dense_type=dense_type,
                sparse_type=sparse_type,
                upsert_meta=upsert_meta,
            )
        )
    except self.MaxRetriesExceededError:
        safe_remove(jsonl_path)
        asyncio.run(fail_job(job_id, "Max retries exceeded in embed stage"))
        raise
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_backoff(self))


@celery_app.task(
    bind=True, max_retries=CELERY_MAX_RETRIES,
    queue="workspace_dbwrite",
    name="workers.ingest_worker.dbwrite_workspace_task",
)
def dbwrite_workspace_task(self, emb_jsonl_path: str, upsert_meta: dict) -> dict:
    job_id = upsert_meta.get("job_id", "")
    try:
        from service.workspace_qdrant_service import workspace_qdrant_service
        result = workspace_qdrant_service.upsert_from_emb_file(emb_jsonl_path, upsert_meta)
        if job_id:
            asyncio.run(increment_upserted(job_id, result.get("upserted", 0)))
        return result
    except self.MaxRetriesExceededError:
        safe_remove(emb_jsonl_path)
        if job_id:
            asyncio.run(fail_job(job_id, "Max retries exceeded in dbwrite stage"))
        raise
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_backoff(self))

@celery_app.task(
    bind=True, max_retries=CELERY_MAX_RETRIES,
    queue="enterprise_chunk",
    name="workers.ingest_worker.chunk_enterprise_task",
)
def chunk_enterprise_task(
    self,
    job_id: str,
    file_path: str,
    file_name: str,
) -> dict:
    try:
        result = asyncio.run(
            run_enterprise_chunk(
                job_id=job_id,
                file_path=file_path,
                file_name=file_name,
            )
        )
        return result
    except self.MaxRetriesExceededError:
        safe_remove(file_path)
        asyncio.run(fail_job(job_id, "Max retries exceeded in enterprise chunk stage"))
        raise
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_backoff(self))
    finally:
        safe_remove(file_path)



@celery_app.task(
    bind=True, max_retries=CELERY_MAX_RETRIES,
    queue="enterprise_embed",
    name="workers.ingest_worker.embed_enterprise_task",
)
def embed_enterprise_task(
    self,
    job_id: str,
    jsonl_path: str,
    page_id: str,
    dense_type: str,
    sparse_type: str,
) -> dict:
    try:
        return asyncio.run(
            run_enterprise_embed(
                job_id=job_id,
                jsonl_path=jsonl_path,
                page_id=page_id,
                dense_type=dense_type,
                sparse_type=sparse_type,
            )
        )
    except self.MaxRetriesExceededError:
        safe_remove(jsonl_path)
        asyncio.run(fail_job(job_id, "Max retries exceeded in enterprise embed stage"))
        raise
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_backoff(self))



@celery_app.task(
    bind=True, max_retries=CELERY_MAX_RETRIES,
    queue="enterprise_dbwrite",
    name="workers.ingest_worker.dbwrite_enterprise_task",
)
def dbwrite_enterprise_task(
    self,
    emb_jsonl_path: str,
    page_id: str,
    job_id: str = "",
) -> dict:
    try:
        from service.enterprise_qdrant_service import enterprise_qdrant_service
        result = enterprise_qdrant_service.upsert_from_emb_file(
            emb_jsonl_path=emb_jsonl_path,
            page_id=page_id,
        )
        if job_id:
            asyncio.run(increment_upserted(job_id, result.get("upserted", 0)))
        return result
    except self.MaxRetriesExceededError:
        safe_remove(emb_jsonl_path)
        if job_id:
            asyncio.run(fail_job(job_id, "Max retries exceeded in enterprise dbwrite stage"))
        raise
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_backoff(self))

'''
@celery_app.task(
    bind=True, max_retries=CELERY_MAX_RETRIES,
    queue="enterprise_chunk",
    name="workers.ingest_worker.ingest_confluence_task",
)
def ingest_confluence_task(self, page_id: str) -> dict:
    try:
        data   = {"page": {"id": page_id}}
        result = asyncio.run(_run_confluence_ingest(data))
        return result
    except self.MaxRetriesExceededError:
        raise
    except Exception as exc:
        raise self.retry(exc=exc, countdown=_backoff(self))



async def _run_confluence_ingest(data: dict) -> dict:
    from service import document_processor
    page_id = str(data.get("page", {}).get("id", ""))
    await document_processor.extract(data, "CONFLUENCE")
    return {"status": "success", "page_id": page_id}
'''