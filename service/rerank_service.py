import logging
import asyncio
from service.model_services import RerankerFactory
from schemas.reranker_dto import RerankDocument
import os

logger = logging.getLogger(__name__)
RETRIES = int(os.getenv("RETRIES", 5))
DELAY = int(os.getenv("DELAY", 3))

class RerankService:
    def __init__(self):
        self.client = RerankerFactory.get_instance()

    async def check_reranker_connectivity(self) -> bool:
        logger.info("--- [Reranker] Checking connectivity ---")
        for attempt in range(RETRIES):
            try:
                dummy_doc = [RerankDocument(content="test")]
                await self.client.rerank(query="ping", documents=dummy_doc, top_n=1)
                logger.info("--- [Reranker] Service Ready ---")
                return True
            except Exception as e:
                logger.warning(f"[Reranker] attempt {attempt + 1} failed: {repr(e)}")
                if attempt < RETRIES - 1:
                    await asyncio.sleep(DELAY)

        logger.error("--- [Reranker] Service unreachable after retries ---")
        return False

    async def rerank(self, query: str, documents: list, top_n: int = 5):
        if not documents:
            return []

        try:
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
                original_doc = documents[item.index]
                original_doc['rerank_score'] = item.rerank_score
                reranked_results.append(original_doc)

            return reranked_results

        except Exception as e:
            logger.error(f"--- [Reranker] Scoring error: {repr(e)} ---")
            return documents[:top_n]

rerank_service = RerankService()