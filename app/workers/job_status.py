from __future__ import annotations

import json
import logging
import os
import time

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_BROKER_URL = os.getenv("REDIS_BROKER_URL", "redis://localhost:6379/0")
REDIS_CACHE_TTL  = int(os.getenv("REDIS_CACHE_TTL", 86400))
REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT",5))

_fastapi_client: aioredis.Redis | None = None


def set_redis_client(client: aioredis.Redis) -> None:
    """Called once at FastAPI startup to inject a long-lived pooled client."""
    global _fastapi_client
    _fastapi_client = client


def _get_redis() -> aioredis.Redis:
    """
    FastAPI  → returns the long-lived injected client (connection pool reused).
    Celery   → _fastapi_client is None, creates a fresh client per asyncio.run().
    """
    if _fastapi_client is not None:
        return _fastapi_client
    return aioredis.Redis.from_url(REDIS_BROKER_URL, socket_timeout=REDIS_SOCKET_TIMEOUT)


def _key(job_id: str) -> str:
    return f"job_status:{job_id}"


async def init_job(job_id: str, file_name: str, total_files: int = 1) -> None:
    payload = {
        "job_id": job_id,
        "file_name": file_name,
        "total_files": total_files,
        "status": "CHUNKING",
        "error": None,
        "chunks": 0,
        "file_size_bytes": 0,
        "avg_chunk_size": 0,
        "min_chunk_size": 0,
        "max_chunk_size": 0,
        "chunk_duration_ms": 0,
        "chunks_per_second": 0.0,
        "batches_done": 0,
        "chunks_embedded": 0,
        "embed_duration_ms": 0,
        "chunks_per_second_embed": 0.0,
        "backpressure_hits": 0,
        "upserted": 0,
        "dbwrite_duration_ms": 0,
        "expected_batches":  0,   
        "completed_batches": 0, 
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    client = _get_redis()
    try:
        await client.setex(_key(job_id), REDIS_CACHE_TTL, json.dumps(payload))
    finally:
        if _fastapi_client is None:
            await client.aclose()


async def update_job(job_id: str, **fields) -> None:
    client = _get_redis()
    try:
        raw = await client.get(_key(job_id))
        if not raw:
            return
        payload = json.loads(raw)
        payload.update({**fields, "updated_at": time.time()})
        await client.setex(_key(job_id), REDIS_CACHE_TTL, json.dumps(payload))
    except Exception as e:
        logger.warning(f"[JobStatus] update_job failed for {job_id}: {e}")
    finally:
        if _fastapi_client is None:
            await client.aclose() 


async def get_job(job_id: str) -> dict | None:
    client = _get_redis()
    try:
        raw = await client.get(_key(job_id))
        if not raw:
            return None
        result = json.loads(raw)
        return result if isinstance(result, dict) else None
    except Exception:
        return None
    finally:
        if _fastapi_client is None:
            await client.aclose() 


async def fail_job(job_id: str, error: str) -> None:
    await update_job(job_id, status="FAILED", error=error)


async def increment_upserted(job_id: str, count: int) -> None:
    client = _get_redis()
    try:
        key = _key(job_id)
        for attempt in range(10):
            async with client.pipeline() as pipe:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    if not raw:
                        return

                    payload = json.loads(raw)
                    payload["upserted"] = payload.get("upserted", 0) + count
                    payload["completed_batches"] = payload.get("completed_batches", 0) + 1
                    payload["updated_at"] = time.time()

                    expected = payload.get("expected_batches", 1)
                    completed = payload["completed_batches"]
                    if completed >= expected and expected > 0:
                        payload["status"] = "DONE"

                    pipe.multi()
                    await pipe.setex(key, REDIS_CACHE_TTL, json.dumps(payload))
                    await pipe.execute()  
                    return              

                except aioredis.WatchError:
                    logger.debug(
                        f"[JobStatus] increment_upserted watch conflict "
                        f"job={job_id} attempt={attempt + 1}, retrying"
                    )
                    continue           

        logger.warning(
            f"[JobStatus] increment_upserted failed after 10 attempts job={job_id}"
        )
    except Exception as e:
        logger.warning(f"[JobStatus] increment_upserted failed for {job_id}: {e}")
    finally:
        if _fastapi_client is None:
            await client.aclose()