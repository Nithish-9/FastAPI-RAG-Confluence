from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from typing import Generator, Iterator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

CHUNK_DIR = os.getenv("CHUNK_STORE_DIR", "/data/chunks")


def chunk_jsonl_path(job_id: str) -> str:
    os.makedirs(CHUNK_DIR, exist_ok=True)
    return os.path.join(CHUNK_DIR, f"{job_id}.jsonl")


def write_chunks_to_jsonl(
    chunks: list,
    job_id: str,
    raw: bool = False,        
) -> tuple[str, int]:
    path  = chunk_jsonl_path(job_id)
    count = 0
    with open(path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            record = chunk if raw else {
                "content":        chunk.content,
                "raw_content":    chunk.raw_content,
                "symbol":         chunk.symbol,
                "language":       chunk.language,
                "chunk_index":    chunk.chunk_index,
                "file_name":      chunk.file_name,
                "file_path":      chunk.file_path,
                "workspace_path": chunk.workspace_path,
                "start_line":     chunk.start_line,
                "end_line":       chunk.end_line,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    logger.info(f"[ChunkIO] Wrote {count} chunks → {path}")
    return path, count


def stream_chunks_from_jsonl(path: str) -> Generator[dict, None, None]:
    """
    Read JSONL file line by line — O(1) memory regardless of chunk count.
    """
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def safe_remove(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
            logger.info(f"[ChunkIO] Deleted {path}")
    except Exception as e:
        logger.warning(f"[ChunkIO] Failed to delete {path}: {e}")

def emb_jsonl_path(job_id: str, batch_idx: int) -> str:
    """Path for one embedded batch file."""
    os.makedirs(CHUNK_DIR, exist_ok=True)
    return os.path.join(CHUNK_DIR, f"{job_id}_b{batch_idx}.emb.jsonl")


def write_embedded_batch(
    job_id: str,
    batch_idx: int,
    batch_chunks: list[dict],
    dense_vecs: list[list[float]],
    sparse_vecs: list,                 
) -> str:
    """
    Write one embedded batch to disk as JSONL.
    Sparse indices/values serialised as plain lists — JSON-safe.
    Returns the file path.
    """
    path = emb_jsonl_path(job_id, batch_idx)
    with open(path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(batch_chunks):
            sv = sparse_vecs[i]
            record = {
                "chunk":       chunk,
                "dense_vec":   dense_vecs[i],
                "sparse_indices": list(sv.indices),
                "sparse_values":  list(sv.values),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def stream_embedded_batch(path: str):
    """Stream one .emb.jsonl file line by line."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)