import logging
import asyncio
from typing import List,Tuple
from service.model_services import DenseModelFactory, SparseModelFactory
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", 32))

class EmbeddingService:
    def __init__(self):
        self.dense_client = DenseModelFactory.get_instance()
        self.sparse_client = SparseModelFactory.get_instance()

    async def _check_service(self, service_name: str, client_call) -> bool:
        logger.info(f"--- [Embed] Checking {service_name} Service connectivity ---")
        try:
            await client_call(["ping"])
            logger.info(f"--- [Embed] {service_name} Service Ready ---")
            return True
        except Exception as e:
            logger.error(f"--- [Embed] {service_name} Service unreachable: {repr(e)} ---")
            return False

    async def check_dense_connectivity(self) -> bool:
        return await self._check_service("Dense", self.dense_client.get_dense_embeddings)

    async def check_sparse_connectivity(self) -> bool:
        return await self._check_service("Sparse", self.sparse_client.get_sparse_embeddings)

    async def get_combined_embeddings(self, texts: List[str]) -> Tuple[List[List[float]], List[dict]]:
        all_dense = []
        all_sparse = []

        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            logger.info(f"--- [Embed] Processing batch {i//EMBED_BATCH_SIZE + 1} (size: {len(batch)}) ---")
            
            try:
                dense_task = self.dense_client.get_dense_embeddings(batch)
                sparse_task = self.sparse_client.get_sparse_embeddings(batch)
                
                dense_res, sparse_res = await asyncio.gather(dense_task, sparse_task)
                
                all_dense.extend([item.embedding for item in dense_res.data])
                all_sparse.extend([item.embedding for item in sparse_res.data])

            except Exception as e:
                logger.error(f"--- [Embed] Error in batch starting at index {i}: {repr(e)} ---")
                raise e

        return all_dense, all_sparse

embed_service = EmbeddingService()