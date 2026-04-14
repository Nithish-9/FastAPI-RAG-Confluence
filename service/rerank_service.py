import logging
import asyncio
from fastembed.rerank.cross_encoder import TextCrossEncoder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class RerankService:
    def __init__(self):
        self.model_name = "jinaai/jina-reranker-v1-turbo-en" 
        self.model = None
        self.is_reranker_ready = False

    def load_reranker_model(self):
        logger.info(f"--- [Reranker] Loading {self.model_name} ---")
        try:
            self.model = TextCrossEncoder(model_name=self.model_name)
            self.is_reranker_ready = True
            logger.info("--- [Reranker] Model Ready ---")
            return True
        except Exception as e:
            logger.error(f"--- [Reranker] Failed to load model: {e} ---")
            return False

    async def rerank(self, query: str, documents: list, top_n: int = 5):
        if not documents or not self.is_reranker_ready:
            return documents[:top_n]

        return await asyncio.to_thread(self._run_scoring, query, documents, top_n)

    def _run_scoring(self, query: str, documents: list, top_n: int):
        try:
            texts = [doc.get('content', '') for doc in documents]

            scores = list(self.model.rerank(query, texts))

            for i, score in enumerate(scores):
                documents[i]['rerank_score'] = float(score)

            reranked = sorted(
                documents,
                key=lambda x: x.get('rerank_score', 0.0),
                reverse=True
            )

            return reranked[:top_n]

        except Exception as e:
            logger.error(f"--- [Reranker] Scoring error: {e} ---")
            return documents[:top_n]


rerank_service = RerankService()