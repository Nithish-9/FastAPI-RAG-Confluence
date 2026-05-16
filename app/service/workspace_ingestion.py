from __future__ import annotations

import asyncio
import base64
import logging
import os

from service.code_parser import code_parser
from service.generate_embedding import embed_service
from service.workspace_qdrant_service import workspace_qdrant_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def decode_user_identity(raw_header: str) -> tuple[str, str]:
    """
    Decode the base64-encoded email from the request header.

    Returns
    -------
    user_id  : base64 string (stored in collection for isolation)
    email_id : plain email string (stored for human-readable reference)
    """
    token = raw_header.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    try:
        padded = token + "=" * (-len(token) % 4)
        email_id = base64.b64decode(padded).decode("utf-8").strip()
    except Exception:
        email_id = token

    user_id = token 
    return user_id, email_id


class WorkspaceIngestionService:

    async def ingest(
        self,
        file_content: bytes,
        file_name: str,
        file_extension: str,
        path: str,
        path_id: str,
        workspace_id: str,
        workspace_path: str,
        content_id: str,
        raw_user_header: str,
    ) -> dict:
        """
        Full ingestion pipeline for a single workspace file.

        Returns a status dict describing what happened.
        """
        user_id, email_id = decode_user_identity(raw_user_header)

        logger.info(
            f"--- [WorkspaceIngest] Start: user={email_id} "
            f"path={path} content_id={content_id[:12]}... ---"
        )

        already_indexed = await asyncio.to_thread(
            workspace_qdrant_service.is_already_indexed, user_id, workspace_id,path_id, content_id
        )
        if already_indexed:
            logger.info(
                f"--- [WorkspaceIngest] Skipped (unchanged): {file_name} ---"
            )
            return {"skipped": True, "reason": "content_id unchanged"}

        await asyncio.to_thread(
            workspace_qdrant_service.delete_by_path_ids, user_id, [path_id]
        )

        chunks = await asyncio.to_thread(
            code_parser.parse_file,
            file_content,
            file_name,
            file_extension,
            path,
            workspace_path,
        )

        if not chunks:
            logger.warning(
                f"--- [WorkspaceIngest] No chunks produced for {file_name} ---"
            )
            return {"skipped": True, "reason": "no chunks produced"}

        logger.info(
            f"--- [WorkspaceIngest] {len(chunks)} chunks from {file_name} "
            f"({chunks[0].language}) ---"
        )

        texts = [c.content for c in chunks] 
        dense_vecs, sparse_vecs = await embed_service.get_combined_embeddings(texts)

        await asyncio.to_thread(
            workspace_qdrant_service.upsert_chunks,
            chunks,
            dense_vecs,
            sparse_vecs,
            user_id,
            email_id,
            content_id,
            workspace_id,
            path_id,
            path,
            file_name,
            file_extension,
        )

        logger.info(
            f"--- [WorkspaceIngest] Done: {file_name} "
            f"({len(chunks)} chunks upserted) ---"
        )
        return {"skipped": False, "chunks_upserted": len(chunks)}



workspace_ingestion_service = WorkspaceIngestionService()
