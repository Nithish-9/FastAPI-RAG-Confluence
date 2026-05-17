from __future__ import annotations

import logging
import aiofiles
import os
import asyncio

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from core.state import system_state
from schemas.workspace_dto import (
    DeleteIndexRequest,
    WorkspaceChunkResult,
    WorkspaceRetrieveRequest,
    WorkspaceRetrieveResponse,
)
from service.generate_embedding import embed_service
from workers.ingest_worker import ingest_file_task
from service.workspace_qdrant_service import workspace_qdrant_service
from celery.result import AsyncResult
from workers.ingest_worker import celery_app
from service.workspace_ingestion import decode_user_identity

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace", tags=["workspace"])

MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def _require_system_ready():
    if not system_state.is_system_ready():
        raise HTTPException(
            status_code=503,
            detail="Search infrastructure is not fully ready. Retry shortly.",
        )


def _require_user_header(x_user_email: str | None) -> str:
    if not x_user_email or not x_user_email.strip():
        raise HTTPException(
            status_code=401,
            detail="X-User-Email header is required (base64-encoded email).",
        )
    return x_user_email.strip()


@router.post("/create-index")
async def create_index(
    content_id: str = Form(..., description="SHA-256 of file content"),
    workspace_id: str = Form(..., description="SHA-256 of workspace root path"),
    workspace_path: str = Form(...,description="Absolute path of workspace root on client"),
    path: str = Form(..., description="Absolute file path on client"),
    path_id: str = Form(..., description="SHA-256 of file path"),
    file_name: str = Form(..., description="e.g. LoanService.java"),
    file_extension: str = Form(..., description="e.g. .java"),
    file_data: UploadFile = File(..., description="File bytes (multipart)"),
    x_user_email: str | None = Header(None, alias="X-User-Email"),
):
    """
    Ingest a single workspace file.

    The Go client (nexus) sends this as multipart/form-data.
    Dedup: if (path_id + content_id) already exists, ingestion is skipped.
    """
    _require_system_ready()
    raw_header = _require_user_header(x_user_email)

    file_bytes = await file_data.read(MAX_FILE_SIZE_BYTES + 1)
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_MB} MB.",
        )
    
    temp_path = f"/shared/uploads/{path_id}_{content_id[:12]}"
    async with aiofiles.open(temp_path, "wb") as f:
        await f.write(file_bytes)

    try:
        task = ingest_file_task.delay(
            file_path=temp_path, 
            file_name=file_name,
            file_extension=file_extension,
            path=path,
            path_id=path_id,
            workspace_id=workspace_id,
            workspace_path=workspace_path,
            content_id=content_id,
            raw_user_header=raw_header,
        )
        return {"status": "queued", "task_id": task.id, "file_name": file_name}
    except Exception as e:
        logger.error(f"[WorkspaceRouter] create-index error: {repr(e)}")
        os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete-index")
async def delete_index(
    request: DeleteIndexRequest,
    x_user_email: str | None = Header(None, alias="X-User-Email"),
):
    """
    Bulk-delete all chunks for the given path_ids.

    The Go delete-worker calls this with node.ChildFilePathIDs so it never
    has to traverse sub-trees again.
    """
    _require_system_ready()
    raw_header = _require_user_header(x_user_email)

    user_id, _ = decode_user_identity(raw_header)

    if not request.path_ids:
        return {"status": "success", "deleted_path_ids": 0}

    try:
        await _run_delete(user_id, request.workspace_id,request.path_ids)
        return {
            "status": "success",
            "deleted_path_ids": len(request.path_ids),
        }
    except Exception as e:
        logger.error(f"[WorkspaceRouter] delete-index error: {repr(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def _run_delete(user_id: str, workspace_id: str,path_ids: list[str]):
    await asyncio.to_thread(
        workspace_qdrant_service.delete_by_path_ids, user_id, workspace_id,path_ids
    )


@router.post("/retrieve", response_model=WorkspaceRetrieveResponse)
async def retrieve(
    request: WorkspaceRetrieveRequest,
    x_user_email: str | None = Header(None, alias="X-User-Email"),
):
    """
    Hybrid semantic search over a user's workspace codebase.

    Designed to be called as an LLM tool:
      - First call: supply query + workspace_id → get back chunks with path_id / chunk_index.
      - Follow-up: supply path_id and/or chunk_index to drill into a specific file/chunk.

    Returns reranked results with full metadata so the LLM can reason about
    which file / symbol each chunk belongs to.
    """
    _require_system_ready()
    raw_header = _require_user_header(x_user_email)

    user_id, _ = decode_user_identity(raw_header)

    try:
        dense_vecs, sparse_vecs = await embed_service.get_combined_embeddings(
            "code",
            "text",
            [request.query]
        )

        results = await workspace_qdrant_service.hybrid_search(
            query_text=request.query,
            query_dense=dense_vecs[0],
            query_sparse=sparse_vecs[0],
            user_id=user_id,
            workspace_id=request.workspace_id,
            top_k=request.top_k,
            path_id=request.path_id,
            chunk_index=request.chunk_index,
        )

        data = []
        for r in results:
            data.append(
                WorkspaceChunkResult(
                    content=r.get("content", ""),
                    file_name=r.get("file_name", ""),
                    file_extension=r.get("file_extension", ""),
                    path=r.get("path", ""),
                    path_id=r.get("path_id", ""),
                    workspace_id=r.get("workspace_id", ""),
                    chunk_index=r.get("chunk_index", 0),
                    content_id=r.get("content_id", ""),
                    symbol=r.get("symbol"),
                    language=r.get("language"),
                    rrf_score=r.get("rrf_score"),
                    rerank_score=r.get("rerank_score"),
                )
            )

        return WorkspaceRetrieveResponse(
            status="success",
            count=len(data),
            data=data,
        )

    except Exception as e:
        logger.error(f"[WorkspaceRouter] retrieve error: {repr(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/index-status/{task_id}")
async def index_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "status": result.status,   # PENDING, STARTED, SUCCESS, FAILURE, RETRY
        "result": result.result if result.ready() else None,
    }
