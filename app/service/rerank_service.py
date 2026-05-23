import logging
import os
from typing import List, Any
from service.model_services import InferenceFactory
from schemas.reranker_dto import RerankDocument

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class RerankService:
    def __init__(self):
        self.client = InferenceFactory.get_reranker()

    async def check_reranker_connectivity(self) -> bool:
        logger.info("--- [Reranker] Checking connectivity ---")
        try:
            dummy_doc = [RerankDocument(content="ping")]
            await self.client.rerank(query="ping", documents=dummy_doc, top_n=1)
            logger.info("--- [Reranker] Service Ready ---")
            return True
        except Exception as e:
            logger.error(f"--- [Reranker] Service unreachable: {repr(e)} ---")
            return False

    async def rerank(self, query: str, documents: List[dict], top_n: int = 5) -> List[dict]:
        if not documents:
            return []

        try:
            MAX_RERANK_CANDIDATES = int(os.getenv("MAX_RERANK_CANDIDATES", 100))
            if len(documents) > MAX_RERANK_CANDIDATES:
                logger.warning(f"--- [Reranker] Truncating candidates from {len(documents)} to {MAX_RERANK_CANDIDATES} ---")
                documents = documents[:MAX_RERANK_CANDIDATES]

            rerank_docs = [
                RerankDocument(content=doc.get('content', '')) 
                for doc in documents
            ]

            response = await self.client.rerank(
                query=query, 
                documents=rerank_docs, 
                top_n=top_n
            )

            reranked_results = []
            for item in response.data:
                if item.index < len(documents):
                    original_doc = documents[item.index]
                    original_doc['rerank_score'] = item.rerank_score
                    reranked_results.append(original_doc)

            return reranked_results

        except Exception as e:
            logger.error(f"--- [Reranker] Scoring error: {repr(e)}. Falling back to initial order. ---")
            return documents[:top_n]

rerank_service = RerankService()