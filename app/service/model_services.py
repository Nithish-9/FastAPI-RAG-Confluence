import os
import httpx
import logging
import urllib3
from abc import ABC, abstractmethod
from typing import List, Union, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from schemas.dense_dto import (DenseEmbedRequest, DenseEmbedResponse)
from schemas.sparse_dto import (SparseEmbedRequest, SparseEmbedResponse,)
from schemas.reranker_dto import (RerankRequest, RerankResponse)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

import os
import httpx
import logging
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

TOTAL_TIMEOUT = float(os.getenv("HTTP_TOTAL_TIMEOUT", 120.0))
CONNECT_TIMEOUT = float(os.getenv("HTTP_CONNECT_TIMEOUT", 10.0))

MAX_CONNECTIONS = int(os.getenv("HTTP_MAX_CONNECTIONS", 100))
MAX_KEEPALIVE = int(os.getenv("HTTP_MAX_KEEPALIVE", 20))

MAX_RETRIES = int(os.getenv("INFERENCE_MAX_RETRIES", 3))
RETRY_MIN = int(os.getenv("INFERENCE_RETRY_MIN_WAIT", 2))
RETRY_MAX = int(os.getenv("INFERENCE_RETRY_MAX_WAIT", 10))

VERIFY_SSL = os.getenv("HTTP_VERIFY_SSL", "true").lower() == "true"

_client_options = {
    "timeout": httpx.Timeout(TOTAL_TIMEOUT, connect=CONNECT_TIMEOUT),
    "verify": VERIFY_SSL,
    "limits": httpx.Limits(
        max_keepalive_connections=MAX_KEEPALIVE, 
        max_connections=MAX_CONNECTIONS
    )
}

_shared_client: Optional[httpx.AsyncClient] = None

def get_http_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        logger.info(f"--- [HTTP] Creating shared client (Pool: {MAX_CONNECTIONS}, Timeout: {TOTAL_TIMEOUT}s) ---")
        _shared_client = httpx.AsyncClient(**_client_options)
    return _shared_client

def inference_retry():
    return retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=RETRY_MIN, max=RETRY_MAX),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying inference call... Attempt {retry_state.attempt_number} "
            f"Wait: {retry_state.next_action.sleep if retry_state.next_action else '0'}s"
        ),
        reraise=True
    )

class BaseModel(ABC):
    api_key: Optional[str] = None
    def __init__(self):
        self.client = get_http_client()

    @inference_retry()
    async def _make_call(self, url: str, payload: Union[DenseEmbedRequest, SparseEmbedRequest, RerankRequest], response_model):
        headers = {"Authorization": f"Bearer {self.api_key}"} if hasattr(self, 'api_key') and self.api_key else {}
        
        response = await self.client.post(
            url, 
            json=payload.model_dump(exclude_none=True), 
            headers=headers
        )
        
        if response.status_code != 200:
            logger.error(f"Error from {url}: {response.status_code} - {response.text}")
        
        response.raise_for_status()
        return response_model(**response.json())


class DenseModelInterface(ABC):
    @abstractmethod
    async def get_dense_embeddings(self, text: Union[str, List[str]]) -> DenseEmbedResponse:
        pass

class BaseDenseModel(BaseModel, DenseModelInterface):
    def __init__(self):
        super().__init__()
        self.url = str(os.getenv("DENSE_URL"))
        self.api_key = os.getenv("DENSE_API_KEY")
        self.model = os.getenv("DENSE_MODEL")
        self.mode_dim = int(os.getenv("DENSE_MODEL_DIM", 0))

class HostedDenseModel(BaseDenseModel):
    async def get_dense_embeddings(self, text: Union[str, List[str]]) -> DenseEmbedResponse:
        payload = DenseEmbedRequest(input=text, model=self.model)
        return await self._make_call(self.url, payload, DenseEmbedResponse)

class LocalDenseModel(BaseDenseModel):
    async def get_dense_embeddings(self, text: Union[str, List[str]]) -> DenseEmbedResponse:
        target_url = f"{self.url.rstrip('/')}/text-embedding"
        payload = DenseEmbedRequest(input=text, dimension=self.mode_dim)
        return await self._make_call(target_url, payload, DenseEmbedResponse)

class DenseModelFactory:
    @staticmethod
    def get_instance() -> DenseModelInterface:
        if os.getenv("DENSE_HOSTED", "false").lower() == "true":
            return HostedDenseModel()
        return LocalDenseModel()


class SparseModelInterface(ABC):
    @abstractmethod
    async def get_sparse_embeddings(self, text: Union[str, List[str]], top_k: int = 50) -> SparseEmbedResponse:
        pass

class BaseSparseModel(BaseModel, SparseModelInterface):
    def __init__(self):
        super().__init__()
        self.url = str(os.getenv("SPARSE_URL"))
        self.api_key = os.getenv("SPARSE_API_KEY")
        self.model = os.getenv("SPARSE_MODEL")

class HostedSparseModel(BaseSparseModel):
    async def get_sparse_embeddings(self, text: Union[str, List[str]], top_k: int = 50) -> SparseEmbedResponse:
        payload = SparseEmbedRequest(input=text, model=self.model, top_k=top_k)
        return await self._make_call(self.url, payload, SparseEmbedResponse)

class LocalSparseModel(BaseSparseModel):
    async def get_sparse_embeddings(self, text: Union[str, List[str]], top_k: int = 50) -> SparseEmbedResponse:
        target_url = f"{self.url.rstrip('/')}/sparse-text-embedding"
        payload = SparseEmbedRequest(input=text, top_k=top_k)
        return await self._make_call(target_url, payload, SparseEmbedResponse)

class SparseModelFactory:
    @staticmethod
    def get_instance() -> SparseModelInterface:
        if os.getenv("SPARSE_HOSTED", "false").lower() == "true":
            return HostedSparseModel()
        return LocalSparseModel()

class RerankerInterface(ABC):
    @abstractmethod
    async def rerank(self, query: str, documents: list, top_n: int = 5) -> RerankResponse:
        pass

class BaseReranker(BaseModel, RerankerInterface):
    def __init__(self):
        super().__init__()
        self.url = str(os.getenv("RERANKER_URL"))
        self.api_key = os.getenv("RERANKER_API_KEY")
        self.model = os.getenv("RERANKER_MODEL")

class HostedReranker(BaseReranker):
    async def rerank(self, query: str, documents: list, top_n: int = 5) -> RerankResponse:
        payload = RerankRequest(query=query, top_n=top_n, documents=documents, model=self.model, return_documents=True)
        return await self._make_call(self.url, payload, RerankResponse)

class LocalReranker(BaseReranker):
    async def rerank(self, query: str, documents: list, top_n: int = 5) -> RerankResponse:
        target_url = f"{self.url.rstrip('/')}/text-cross-encoder"
        payload = RerankRequest(query=query, top_n=top_n, documents=documents, return_documents=True)
        return await self._make_call(target_url, payload, RerankResponse)

class RerankerFactory:
    @staticmethod
    def get_instance() -> RerankerInterface:
        if os.getenv("RERANKER_HOSTED", "false").lower() == "true":
            return HostedReranker()
        return LocalReranker()