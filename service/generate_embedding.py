import logging
import asyncio
from typing import List
from .model_services import DenseModelFactory, SparseModelFactory
import os

logger = logging.getLogger(__name__)

RETRIES = int(os.getenv("RETRIES", 5))
DELAY = int(os.getenv("DELAY", 3))

class EmbeddingService:
    def __init__(self):
        self.dense_client = DenseModelFactory.get_instance()
        self.sparse_client = SparseModelFactory.get_instance()

    async def check_dense_connectivity(self) -> bool:
        logger.info("--- [Embed] Checking Dense Service connectivity ---")
        for attempt in range(RETRIES):
            try:
                await self.dense_client.get_dense_embeddings(["ping"])
                logger.info("--- [Embed] Dense Service Ready ---")
                return True
            except Exception as e:
                logger.warning(f"[Embed] Dense attempt {attempt + 1} failed: {e}")
                if attempt < RETRIES - 1:
                    await asyncio.sleep(DELAY)
        logger.error("--- [Embed] Dense Service unreachable after retries ---")
        return False

    async def check_sparse_connectivity(self) -> bool:
        logger.info("--- [Embed] Checking Sparse Service connectivity ---")
        for attempt in range(RETRIES):
            try:
                await self.sparse_client.get_sparse_embeddings(["ping"])
                logger.info("--- [Embed] Sparse Service Ready ---")
                return True
            except Exception as e:
                logger.warning(f"[Embed] Sparse attempt {attempt + 1} failed: {e}")
                if attempt < RETRIES - 1:
                    await asyncio.sleep(DELAY)
                    
        logger.error("--- [Embed] Sparse Service unreachable after retries ---")
        return False

    async def get_combined_embeddings(self, texts: List[str]):
        try:
            dense_task = self.dense_client.get_dense_embeddings(texts)
            sparse_task = self.sparse_client.get_sparse_embeddings(texts)
            
            dense_res, sparse_res = await asyncio.gather(dense_task, sparse_task)
            
            dense_vectors = [item.embedding for item in dense_res.data]
            sparse_vectors = [item.embedding for item in sparse_res.data]

            return dense_vectors, sparse_vectors

        except Exception as e:
            logger.error(f"--- [Embed] Error fetching combined embeddings: {e} ---")
            raise e

embed_service = EmbeddingService()