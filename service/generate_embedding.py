from fastembed import TextEmbedding, SparseTextEmbedding
from typing import List
import logging
import asyncio
from core.concurrency import executor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger(__name__)

class EmbeddingService:
    dense_model: TextEmbedding
    sparse_model: SparseTextEmbedding

    def __init__(self):
        self.is_dense_ready = False
        self.is_sparse_ready = False

    def load_dense_model(self):
        try:
            logger.info("--- [Embed] Loading Dense Model (BGE) ---")
            self.dense_model = TextEmbedding(model_name="BAAI/bge-base-en-v1.5")
            self.is_dense_ready = True
            logger.info("--- [Embed] Dense Model Ready ---")
            return True
        except Exception as e:
            logger.error(f"Dense Model load failed: {e}")
            return False

    def load_sparse_model(self):
        try:
            logger.info("--- [Embed] Loading Sparse Model (Splade) ---")
            self.sparse_model = SparseTextEmbedding(model_name="prithivida/Splade_PP_en_v1")
            self.is_sparse_ready = True
            logger.info("--- [Embed] Sparse Model Ready ---")
            return True
        except Exception as e:
            logger.error(f"Sparse Model load failed: {e}")
            return False

    def generate_dense(self, texts: List[str]):
        return list(self.dense_model.embed(texts))

    def generate_sparse(self, texts: List[str]):
        return list(self.sparse_model.embed(texts))
    
    async def get_combined_embeddings(self, texts: List[str]):
        loop = asyncio.get_running_loop()
        
        dense_task = loop.run_in_executor(executor, self.generate_dense, texts)
        sparse_task = loop.run_in_executor(executor, self.generate_sparse, texts)
        
        dense_vecs, sparse_vecs = await asyncio.gather(dense_task, sparse_task)
    
        return dense_vecs, sparse_vecs

embed_service = EmbeddingService()