import os
import asyncio
import logging
import urllib3

import httpx
from abc import ABC, abstractmethod
from typing import List, Optional, Union

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from schemas.dense_dto import DenseEmbedRequest, DenseEmbedResponse
from schemas.sparse_dto import SparseEmbedRequest, SparseEmbedResponse
from schemas.reranker_dto import RerankRequest, RerankResponse

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

# Inference services (embedding + reranker) can be slow on first call
# (model warm-up, large batches). Keep timeouts generous.
TOTAL_TIMEOUT    = float(os.getenv("HTTP_TOTAL_TIMEOUT", 300.0))   # 5 min — covers cold start
CONNECT_TIMEOUT  = float(os.getenv("HTTP_CONNECT_TIMEOUT", 15.0))  # 15s connect

MAX_CONNECTIONS  = int(os.getenv("HTTP_MAX_CONNECTIONS", 100))
MAX_KEEPALIVE    = int(os.getenv("HTTP_MAX_KEEPALIVE", 20))
VERIFY_SSL       = os.getenv("HTTP_VERIFY_SSL", "true").lower() == "true"

MAX_RETRIES      = int(os.getenv("INFERENCE_MAX_RETRIES", 3))
RETRY_MIN        = int(os.getenv("INFERENCE_RETRY_MIN_WAIT", 2))
RETRY_MAX        = int(os.getenv("INFERENCE_RETRY_MAX_WAIT", 10))

_CLIENT_OPTIONS = {
    "timeout": httpx.Timeout(
        TOTAL_TIMEOUT,
        connect=CONNECT_TIMEOUT,
    ),
    "verify": VERIFY_SSL,
    "limits": httpx.Limits(
        max_connections=MAX_CONNECTIONS,
        max_keepalive_connections=MAX_KEEPALIVE,
    ),
}

# ── Shared HTTP client — event-loop aware ─────────────────────────────────────
# httpx.AsyncClient is bound to the event loop it was created in.
# Celery workers create a new event loop per task via asyncio.run(), so we
# must detect loop changes and recreate the client accordingly.

_shared_client: Optional[httpx.AsyncClient] = None
_client_loop:   Optional[asyncio.AbstractEventLoop] = None


def get_http_client() -> httpx.AsyncClient:
    global _shared_client, _client_loop

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    need_new_client = (
        _shared_client is None
        or _shared_client.is_closed
        or _client_loop is not current_loop
    )

    if need_new_client:
        if _shared_client is not None and not _shared_client.is_closed:
            logger.warning(
                "[HTTP] Event loop changed — recreating HTTP client. "
                "Old client will be garbage collected."
            )
        logger.info(
            f"--- [HTTP] Creating shared AsyncClient "
            f"(pool={MAX_CONNECTIONS}, keepalive={MAX_KEEPALIVE}, "
            f"timeout={TOTAL_TIMEOUT}s) ---"
        )
        _shared_client = httpx.AsyncClient(**_CLIENT_OPTIONS)
        _client_loop = current_loop

    assert _shared_client is not None  # ← tells Pylance the value is guaranteed here
    return _shared_client


async def close_http_client() -> None:
    """
    Gracefully close the shared HTTP client.
    Call this from FastAPI lifespan shutdown so connections are cleanly drained.
    """
    global _shared_client, _client_loop
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        logger.info("--- [HTTP] Shared AsyncClient closed ---")
    _shared_client = None
    _client_loop   = None


# ── Retry decorator ───────────────────────────────────────────────────────────

def inference_retry():
    return retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=RETRY_MIN, max=RETRY_MAX),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        before_sleep=lambda state: logger.warning(
            f"[HTTP] Retrying inference call — attempt {state.attempt_number}, "
            f"wait {state.next_action.sleep if state.next_action else 0:.1f}s"
        ),
        reraise=True,
    )


# ── Base model ────────────────────────────────────────────────────────────────

class BaseModel(ABC):
    """
    Base for all inference clients.
    Uses the shared event-loop-aware HTTP client.
    """
    api_key: Optional[str] = None

    def __init__(self):
        # Don't store the client at init time — always fetch it at call time
        # so that Celery workers (which have a fresh event loop per task)
        # always get a client bound to the correct loop.
        pass

    @property
    def client(self) -> httpx.AsyncClient:
        return get_http_client()

    @inference_retry()
    async def _make_call(
        self,
        url: str,
        payload: Union[DenseEmbedRequest, SparseEmbedRequest, RerankRequest],
        response_model,
    ):
        headers = (
            {"Authorization": f"Bearer {self.api_key}"}
            if self.api_key
            else {}
        )

        response = await self.client.post(
            url,
            json=payload.model_dump(exclude_none=True),
            headers=headers,
        )

        if response.status_code != 200:
            # Log as warning — tenacity will retry; only the final failure
            # after all retries should be treated as an error (reraise=True handles it).
            logger.warning(
                f"[HTTP] Non-200 from {url}: "
                f"{response.status_code} — {response.text[:200]}"
            )

        response.raise_for_status()
        return response_model(**response.json())


# ── Dense embedding ───────────────────────────────────────────────────────────

class DenseModelInterface(ABC):
    @abstractmethod
    async def get_dense_embeddings(
        self, text: Union[str, List[str]]
    ) -> DenseEmbedResponse:
        pass


class BaseDenseModel(BaseModel, DenseModelInterface):
    def __init__(self):
        super().__init__()
        self.url      = str(os.getenv("DENSE_URL", ""))
        self.api_key  = os.getenv("DENSE_API_KEY")
        self.model    = os.getenv("DENSE_MODEL")
        self.mode_dim = int(os.getenv("DENSE_MODEL_DIM", 0))


class HostedDenseModel(BaseDenseModel):
    async def get_dense_embeddings(
        self, text: Union[str, List[str]]
    ) -> DenseEmbedResponse:
        payload = DenseEmbedRequest(input=text, model=self.model)
        return await self._make_call(self.url, payload, DenseEmbedResponse)


class LocalDenseModel(BaseDenseModel):
    async def get_dense_embeddings(
        self, text: Union[str, List[str]]
    ) -> DenseEmbedResponse:
        target_url = f"{self.url.rstrip('/')}/text-embedding"
        payload = DenseEmbedRequest(input=text, dimension=self.mode_dim)
        return await self._make_call(target_url, payload, DenseEmbedResponse)


class DenseModelFactory:
    @staticmethod
    def get_instance() -> DenseModelInterface:
        if os.getenv("DENSE_HOSTED", "false").lower() == "true":
            return HostedDenseModel()
        return LocalDenseModel()


# ── Sparse embedding ──────────────────────────────────────────────────────────

class SparseModelInterface(ABC):
    @abstractmethod
    async def get_sparse_embeddings(
        self, text: Union[str, List[str]], top_k: int = 50
    ) -> SparseEmbedResponse:
        pass


class BaseSparseModel(BaseModel, SparseModelInterface):
    def __init__(self):
        super().__init__()
        self.url     = str(os.getenv("SPARSE_URL", ""))
        self.api_key = os.getenv("SPARSE_API_KEY")
        self.model   = os.getenv("SPARSE_MODEL")


class HostedSparseModel(BaseSparseModel):
    async def get_sparse_embeddings(
        self, text: Union[str, List[str]], top_k: int = 50
    ) -> SparseEmbedResponse:
        payload = SparseEmbedRequest(input=text, model=self.model, top_k=top_k)
        return await self._make_call(self.url, payload, SparseEmbedResponse)


class LocalSparseModel(BaseSparseModel):
    async def get_sparse_embeddings(
        self, text: Union[str, List[str]], top_k: int = 50
    ) -> SparseEmbedResponse:
        target_url = f"{self.url.rstrip('/')}/sparse-text-embedding"
        payload = SparseEmbedRequest(input=text, top_k=top_k)
        return await self._make_call(target_url, payload, SparseEmbedResponse)


class SparseModelFactory:
    @staticmethod
    def get_instance() -> SparseModelInterface:
        if os.getenv("SPARSE_HOSTED", "false").lower() == "true":
            return HostedSparseModel()
        return LocalSparseModel()


# ── Reranker ──────────────────────────────────────────────────────────────────

class RerankerInterface(ABC):
    @abstractmethod
    async def rerank(
        self, query: str, documents: list, top_n: int = 5
    ) -> RerankResponse:
        pass


class BaseReranker(BaseModel, RerankerInterface):
    def __init__(self):
        super().__init__()
        self.url     = str(os.getenv("RERANKER_URL", ""))
        self.api_key = os.getenv("RERANKER_API_KEY")
        self.model   = os.getenv("RERANKER_MODEL")


class HostedReranker(BaseReranker):
    async def rerank(
        self, query: str, documents: list, top_n: int = 5
    ) -> RerankResponse:
        payload = RerankRequest(
            query=query,
            top_n=top_n,
            documents=documents,
            model=self.model,
            return_documents=True,
        )
        return await self._make_call(self.url, payload, RerankResponse)


class LocalReranker(BaseReranker):
    async def rerank(
        self, query: str, documents: list, top_n: int = 5
    ) -> RerankResponse:
        target_url = f"{self.url.rstrip('/')}/text-cross-encoder"
        payload = RerankRequest(
            query=query,
            top_n=top_n,
            documents=documents,
            return_documents=True,
        )
        return await self._make_call(target_url, payload, RerankResponse)


class RerankerFactory:
    @staticmethod
    def get_instance() -> RerankerInterface:
        if os.getenv("RERANKER_HOSTED", "false").lower() == "true":
            return HostedReranker()
        return LocalReranker()