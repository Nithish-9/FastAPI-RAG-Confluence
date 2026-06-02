from __future__ import annotations

import asyncio
import logging
import os
import time

import redis

from workers.chunk_io import (
    stream_chunks_from_jsonl,
    write_embedded_batch,
    safe_remove,
)
from workers.job_status import update_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE   = int(os.getenv("EMBED_BATCH_SIZE", 8))
READ_AHEAD_LIMIT   = int(os.getenv("READ_AHEAD_LIMIT", 2))
EMBED_CONCURRENCY  = int(os.getenv("EMBED_CONCURRENCY", 1))
DBWRITE_QUEUE_MAX  = int(os.getenv("DBWRITE_QUEUE_MAX", 500))
BACKPRESSURE_SLEEP = float(os.getenv("BACKPRESSURE_SLEEP", 0.5))
REDIS_BROKER_URL   = os.getenv("REDIS_BROKER_URL", "redis://localhost:6379/0")
REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT",5))

_semaphore_val = int(os.getenv("INFERENCE_SEMAPHORE", "1"))
effective_concurrency = min(_semaphore_val, EMBED_CONCURRENCY)

_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(REDIS_BROKER_URL, socket_timeout=REDIS_SOCKET_TIMEOUT)
    assert isinstance(_redis_client, redis.Redis)
    return _redis_client


def _dbwrite_queue_depth() -> int:
    try:
        depth = _get_redis().llen("enterprise_dbwrite")
        return depth if isinstance(depth, int) else 0
    except Exception:
        return 0


async def run_enterprise_embed(
    job_id: str,
    jsonl_path: str,
    page_id: str,
    dense_type: str,
    sparse_type: str,
) -> dict:
    from service.generate_embedding import embed_service
    from workers.ingest_worker import dbwrite_enterprise_task

    _DONE = object()
    batch_queue: asyncio.Queue = asyncio.Queue(maxsize=READ_AHEAD_LIMIT)

    total_batches = 0
    total_chunks = 0
    backpressure_hits = 0
    lock = asyncio.Lock()

    t0 = time.perf_counter()

    async def producer() -> None:
        batch: list[dict] = []
        for record in stream_chunks_from_jsonl(jsonl_path):
            batch.append(record)
            if len(batch) >= EMBED_BATCH_SIZE:
                await batch_queue.put(batch)
                batch = []
        if batch:
            await batch_queue.put(batch)
        for _ in range(effective_concurrency):
            await batch_queue.put(_DONE)

    async def consumer(consumer_id: int) -> None:
        nonlocal total_batches, total_chunks, backpressure_hits

        while True:
            batch = await batch_queue.get()
            if batch is _DONE:
                batch_queue.task_done()
                return

            try:

                texts = [c["content"] for c in batch]
                dense_vecs, sparse_vecs = await embed_service.get_combined_embeddings(
                    dense_type, sparse_type, texts
                )

                depth = await asyncio.to_thread(_dbwrite_queue_depth)
                while depth >= DBWRITE_QUEUE_MAX:
                    async with lock:
                        backpressure_hits += 1
                    logger.warning(
                        f"[EnterpriseEmbed] job={job_id} consumer={consumer_id} "
                        f"backpressure — sleeping {BACKPRESSURE_SLEEP}s"
                    )
                    await asyncio.sleep(BACKPRESSURE_SLEEP)
                    depth = await asyncio.to_thread(_dbwrite_queue_depth)

                async with lock:
                    batch_idx = total_batches
                    total_batches += 1
                    total_chunks  += len(batch)

                emb_path = await asyncio.to_thread(
                    write_embedded_batch,
                    job_id, batch_idx, batch, dense_vecs, sparse_vecs,
                )

                dbwrite_enterprise_task.apply_async(
                    kwargs={
                        "emb_jsonl_path": emb_path,
                        "page_id": page_id,
                        "job_id": job_id,
                    },
                    queue="enterprise_dbwrite",
                )

                logger.info(
                    f"[EnterpriseEmbed] job={job_id} batch={batch_idx} "
                    f"chunks={len(batch)} → {emb_path}"
                )

            except Exception as e:
                logger.error(
                    f"[EnterpriseEmbed] job={job_id} consumer={consumer_id} "
                    f"batch failed: {repr(e)}"
                )
                await update_job(job_id, status="FAILED", error=str(e))
                raise

            finally:
                batch_queue.task_done()

    try:
        consumers = [
            asyncio.create_task(consumer(i)) for i in range(effective_concurrency)
        ]
        await asyncio.gather(producer(), *consumers)
    except Exception:
        for task in consumers:
            task.cancel()
        await asyncio.gather(*consumers, return_exceptions=True)
        safe_remove(jsonl_path)
        raise

    embed_duration_ms = (time.perf_counter() - t0) * 1000
    chunks_per_second_embed = round(
        total_chunks / (embed_duration_ms / 1000), 2
    ) if embed_duration_ms > 0 else 0.0

    safe_remove(jsonl_path)

    logger.info(
        f"[EnterpriseEmbed] job={job_id} complete — "
        f"{total_chunks} chunks in {total_batches} batches | "
        f"{chunks_per_second_embed} chunks/s | {embed_duration_ms:.0f}ms | "
        f"backpressure_hits={backpressure_hits}"
    )

    await update_job(
        job_id,
        status="WRITING",
        chunks_embedded=total_chunks,
        batches_done=total_batches,
        embed_duration_ms=round(embed_duration_ms, 2),
        chunks_per_second_embed=chunks_per_second_embed,
        backpressure_hits=backpressure_hits,
        expected_batches=total_batches,
    )

    return {"total_chunks": total_chunks, "total_batches": total_batches}