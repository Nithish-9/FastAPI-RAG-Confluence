import logging
import asyncio
from typing import List, Tuple, Any
import os

from service.model_services import InferenceFactory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", 8))


class EmbeddingService:
    def __init__(self):
        pass

    async def _check_service(self, service_name: str, client_call: Any) -> bool:
        logger.info(f"--- [Embed] Checking {service_name} Service connectivity ---")
        try:
            await client_call(["ping"])
            logger.info(f"--- [Embed] {service_name} Service Ready ---")
            return True
        except Exception as e:
            logger.error(f"--- [Embed] {service_name} Service unreachable: {repr(e)} ---")
            return False

    async def check_dense_connectivity(self, dense_type: str = "text") -> bool:
        try:
            client = InferenceFactory.get_dense(dense_type)
            return await self._check_service(f"Dense ({dense_type})", client.get_dense_embeddings)
        except ValueError as e:
            logger.error(f"--- [Embed] Connectivity check aborted: {e} ---")
            return False

    async def check_sparse_connectivity(self, sparse_type: str = "text") -> bool:
        try:
            client = InferenceFactory.get_sparse(sparse_type)
            return await self._check_service(f"Sparse ({sparse_type})", client.get_sparse_embeddings)
        except ValueError as e:
            logger.error(f"--- [Embed] Connectivity check aborted: {e} ---")
            return False

    async def get_combined_embeddings(
        self,
        dense_type: str,
        sparse_type: str,
        texts: List[str],
        batch_size: int | None = None,     
    ) -> Tuple[List[List[float]], List[Any]]:   # List[Any] = SparseEmbedding objects
        all_dense: List[List[float]] = []
        all_sparse: List[Any] = []

        dense_client  = InferenceFactory.get_dense(dense_type)
        sparse_client = InferenceFactory.get_sparse(sparse_type)

        # streaming_embed passes pre-batched texts (len == batch_size already),
        # so effective_batch_size = len(texts) in that path → single iteration,
        # no redundant re-batching. 
        effective_batch_size = batch_size or EMBED_BATCH_SIZE

        for i in range(0, len(texts), effective_batch_size):
            batch = texts[i : i + effective_batch_size]
            batch_chars = sum(len(t) for t in batch)

            logger.info(
                f"[Embed Batch] "
                f"batch={i // effective_batch_size + 1} "
                f"chunks={len(batch)} "
                f"chars={batch_chars}"
            )

            try:
                dense_res, sparse_res = await asyncio.gather(
                    dense_client.get_dense_embeddings(batch),
                    sparse_client.get_sparse_embeddings(batch),
                )

                all_dense.extend([item.embedding for item in dense_res.data])
                all_sparse.extend([item.embedding for item in sparse_res.data])

            except Exception as e:
                logger.error(
                    f"--- [Embed] Error in batch starting at index {i}: {repr(e)} ---"
                )
                raise

        return all_dense, all_sparse


embed_service = EmbeddingService()