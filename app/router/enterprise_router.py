from __future__ import annotations

import logging
import uuid
import os
import asyncio

import aiofiles
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from celery.result import AsyncResult

from core.state import system_state
from schemas.enterprise_dto import DeleteIndexRequest, EnterpriseRetrieveRequest
from service.generate_embedding import embed_service
from service.enterprise_qdrant_service import enterprise_qdrant_service
from workers.ingest_worker import celery_app, ingest_enterprise_task, ingest_confluence_task
from utils import require_system_ready

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enterprise", tags=["enterprise"])

MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


@router.post("/create-index")
async def create_index(file: UploadFile = File(...)):
    """
    Ingest a single enterprise document (PDF, DOCX, TXT, …).

    Saves the upload to shared storage and queues an
    ingest_enterprise_task on the 'enterprise_ingestion' Celery queue.
    The worker delegates to document_processor.extract() which owns
    loading → hashing → dedup → chunking → embedding → upsert.
    """
    require_system_ready()

    file_bytes = await file.read(MAX_FILE_SIZE_BYTES + 1)
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_MB} MB.",
        )

    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename or "")[1]
    temp_path = f"/shared/uploads/enterprise_{file_id}{ext}"

    async with aiofiles.open(temp_path, "wb") as f:
        await f.write(file_bytes)

    try:
        task = ingest_enterprise_task.delay(
            file_path=temp_path,
            file_name=file.filename,
        )
        return {"status": "queued", "task_id": task.id, "file_name": file.filename}
    except Exception as e:
        logger.error(f"[EnterpriseRouter] create-index error: {repr(e)}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/confluence")
async def confluence_webhook(request: Request):
    """
    Receives a Confluence webhook payload and queues ingestion on the
    'enterprise_ingestion' Celery queue.
    """
    data = await request.json()

    page_id = str(data.get("page", {}).get("id", ""))
    if not page_id or page_id == "None":
        raise HTTPException(status_code=400, detail="Missing or invalid page.id in webhook payload")

    task = ingest_confluence_task.delay(page_id=page_id)
    return {"status": "queued", "task_id": task.id, "page_id": page_id}



@router.post("/delete-index")
async def delete_index(request: DeleteIndexRequest):
    """
    Bulk-delete all chunks for the given list of page_ids in the enterprise collection
    """
    require_system_ready()

    if not request.page_ids:
        return {"status": "success", "deleted_page_ids": 0}

    try:
        await asyncio.to_thread(
            enterprise_qdrant_service.delete_by_page_ids, request.page_ids
        )
        return {
            "status": "success",
            "deleted_page_ids": len(request.page_ids),
        }
    except Exception as e:
        logger.error(f"[EnterpriseRouter] delete-index error: {repr(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrieve")
async def retrieve(request: EnterpriseRetrieveRequest):
    """
    Hybrid semantic search over enterprise collection.
    """
    require_system_ready()

    try:
        dense_vecs, sparse_vecs = await embed_service.get_combined_embeddings(
            "text",
            "text",
            [request.query],
        )
        results = await enterprise_qdrant_service.hybrid_search(
            query_text=request.query,
            query_dense=dense_vecs[0],
            query_sparse=sparse_vecs[0],
            limit=request.top_k,
            page_id=request.page_id,
            chunk_index=request.chunk_index,
        )
        return {"status": "success", "count": len(results), "data": results}
    except Exception as e:
        logger.error(f"[EnterpriseRouter] retrieve error: {repr(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index-status/{task_id}")
async def index_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }