import asyncio
import logging
import aiofiles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

from workers.job_status import update_job
from workers.chunk_io import write_chunks_to_jsonl,safe_remove
from workers.ingest_worker import embed_workspace_task

async def run_workspace_chunk(
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
    from service.workspace_ingestion import decode_user_identity
    from service.code_parser import code_parser
    from service.workspace_qdrant_service import workspace_qdrant_service

    await update_job(job_id, status="CHUNKING")
    user_id, email_id = decode_user_identity(raw_user_header)

    already_indexed = await asyncio.to_thread(
        workspace_qdrant_service.is_already_indexed,
        user_id, workspace_id, path_id, content_id,
    )
    if already_indexed:
        safe_remove(file_path)
        await update_job(job_id, status="SKIPPED", error="content_id unchanged")
        return {"skipped": True, "reason": "content_id unchanged"}

    await asyncio.to_thread(
        workspace_qdrant_service.delete_by_path_ids,
        user_id, workspace_id, [path_id],
    )

    async with aiofiles.open(file_path, "rb") as f:
        file_content = await f.read()

    safe_remove(file_path)

    chunks = await asyncio.to_thread(
        code_parser.parse_file,
        file_content, file_name, file_extension, path, workspace_path,
    )
    del file_content

    if not chunks:
        await update_job(job_id, status="SKIPPED", error="no chunks produced")
        return {"skipped": True, "reason": "no chunks produced"}

    sizes = [len(c.content) for c in chunks]
    logger.info(
        f"[ChunkWorker] {file_name}: {len(chunks)} chunks | "
        f"min={min(sizes)} max={max(sizes)} avg={sum(sizes)/len(sizes):.0f}"
    )

    jsonl_path, chunk_count = await asyncio.to_thread(
        write_chunks_to_jsonl, chunks, job_id
    )
    del chunks

    await update_job(job_id, status="EMBEDDING", chunks=chunk_count)

    upsert_meta = {
        "user_id":        user_id,
        "email_id":       email_id,
        "content_id":     content_id,
        "workspace_id":   workspace_id,
        "path_id":        path_id,
        "path":           path,
        "file_name":      file_name,
        "file_extension": file_extension,
        "job_id":         job_id,
    }

    embed_workspace_task.apply_async(
        kwargs={
            "job_id":       job_id,
            "jsonl_path":   jsonl_path,
            "dense_type":   "code",
            "sparse_type":  "text",
            "upsert_meta":  upsert_meta,
        },
        queue="workspace_embed",
    )

    logger.info(
        f"[ChunkWorker] Done: {file_name} → {chunk_count} chunks → "
        f"embed job {job_id} enqueued"
    )
    return {"skipped": False, "job_id": job_id, "chunk_count": chunk_count}
