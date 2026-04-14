import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import logging
import asyncio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

class RerankService:
    def __init__(self):
        self.model_name = "BAAI/bge-reranker-base"
        self.tokenizer = None
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.is_reranker_ready = False

    def load_reranker_model(self):
        logger.info(f"--- [Reranker] Loading {self.model_name} on {self.device} ---")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
            self.is_reranker_ready = True
            logger.info("--- [Reranker] Model Ready ---")
        except Exception as e:
            logger.error(f"--- [Reranker] Failed to load model: {e} ---")

    async def rerank(self, query: str, documents: list, top_n: int = 5):
        if not documents or not self.is_reranker_ready:
            return documents[:top_n]

        return await asyncio.to_thread(self._run_scoring, query, documents, top_n)

    def _run_scoring(self, query: str, documents: list, top_n: int):

        if self.model is None or self.tokenizer is None:
            logger.warning("--- [Reranker] Model or Tokenizer not loaded. Returning raw results. ---")
            return documents[:top_n]

        pairs = [[query, doc.get('content', '')] for doc in documents]
        
        try:
            with torch.no_grad():
                inputs = self.tokenizer(
                    pairs, 
                    padding=True, 
                    truncation=True, 
                    return_tensors='pt', 
                    max_length=512
                ).to(self.device)
                
                logits = self.model(**inputs).logits
                scores = logits.view(-1).cpu().tolist()

            for i, score in enumerate(scores):
                documents[i]['rerank_score'] = float(score)

            reranked = sorted(documents, key=lambda x: x.get('rerank_score', 0.0), reverse=True)
            return reranked[:top_n]

        except Exception as e:
            logger.error(f"--- [Reranker] Scoring error: {e} ---")
            return documents[:top_n]

rerank_service = RerankService()