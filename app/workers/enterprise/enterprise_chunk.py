import asyncio
import logging
import os
import time
import hashlib

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

from workers.job_status import update_job
from workers.chunk_io import write_chunks_to_jsonl,safe_remove


async def run_enterprise_chunk(
    job_id: str,
    file_path: str,
    file_name: str,
) -> dict:
    from service.document_chunking import documentChunker
    from service.enterprise_qdrant_service import enterprise_qdrant_service
    from langchain_community.document_loaders import (
        PyPDFLoader, Docx2txtLoader, TextLoader, UnstructuredFileLoader,
    )

    await update_job(job_id, status="CHUNKING")

    file_size_bytes = os.path.getsize(file_path)
    raw_hash = await asyncio.to_thread(_hash_file_bytes, file_path)

    exists = await asyncio.to_thread(
        enterprise_qdrant_service.check_doc_changed, raw_hash
    )
    if not exists:
        safe_remove(file_path)
        await update_job(job_id, status="SKIPPED", error="content already indexed")
        return {"skipped": True, "reason": "content already indexed"}

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        loader = PyPDFLoader(file_path)
    elif ext in [".docx", ".doc"]:
        loader = Docx2txtLoader(file_path)
    elif ext == ".txt":
        loader = TextLoader(file_path)
    else:
        loader = UnstructuredFileLoader(file_path)

    documents = await asyncio.to_thread(loader.load)
    safe_remove(file_path)

    if not documents:
        await update_job(job_id, status="SKIPPED", error="no content extracted")
        return {"skipped": True, "reason": "no content extracted"}

    combined = "\n".join([d.page_content for d in documents])
    master_doc = documents[0]
    master_doc.page_content = combined
    master_doc.metadata.update({
        "source_type":  ext.replace(".", "").upper(),
        "page_id": raw_hash,
        "filename": file_name,
        "content_hash": raw_hash,
    })

    t0 = time.perf_counter()
    chunks = await asyncio.to_thread(
        documentChunker.process_document, master_doc, raw_hash
    )
    chunk_duration_ms = (time.perf_counter() - t0) * 1000
    del documents, master_doc

    if not chunks:
        await update_job(job_id, status="SKIPPED", error="no chunks produced")
        return {"skipped": True, "reason": "no chunks produced"}

    sizes = [len(c.page_content) for c in chunks]
    chunk_count = len(chunks)
    avg_chunk_size = int(sum(sizes) / chunk_count)
    min_chunk_size = min(sizes)
    max_chunk_size = max(sizes)
    chunks_per_second = round(chunk_count / (chunk_duration_ms / 1000), 2) \
                        if chunk_duration_ms > 0 else 0.0

    logger.info(
        f"[EnterpriseChunkWorker] {file_name}: {chunk_count} chunks | "
        f"min={min_chunk_size} max={max_chunk_size} avg={avg_chunk_size} | "
        f"{chunks_per_second} chunks/s | {chunk_duration_ms:.0f}ms"
    )

    serialisable = [
        {
            "content" : c.page_content,
            "metadata" : c.metadata,
            "chunk_index" : c.metadata.get("chunk_index", i),
        }
        for i, c in enumerate(chunks)
    ]
    del chunks

    jsonl_path, chunk_count = await asyncio.to_thread(
        write_chunks_to_jsonl, serialisable, job_id, raw=True
    )

    await update_job(
        job_id,
        status="EMBEDDING",
        chunks=chunk_count,
        file_size_bytes=file_size_bytes,
        avg_chunk_size=avg_chunk_size,
        min_chunk_size=min_chunk_size,
        max_chunk_size=max_chunk_size,
        chunk_duration_ms=round(chunk_duration_ms, 2),
        chunks_per_second=chunks_per_second,
    )

    from workers.ingest_worker import embed_enterprise_task
    embed_enterprise_task.apply_async(
        kwargs={
            "job_id":      job_id,
            "jsonl_path":  jsonl_path,
            "page_id":     raw_hash,
            "dense_type":   "text",
            "sparse_type":  "text",
        },
        queue="enterprise_embed",
    )

    logger.info(
        f"[EnterpriseChunkWorker] Done: {file_name} → "
        f"{chunk_count} chunks → embed job {job_id} enqueued"
    )
    return {"skipped": False, "job_id": job_id, "chunk_count": chunk_count}

def _hash_file_bytes(file_path: str) -> str:
    """SHA-256 of raw file bytes — stable across loader versions."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()