import os
import httpx
from abc import ABC, abstractmethod
from typing import List, Union

from schemas.dense_dto import (DenseEmbedRequest, DenseEmbedResponse)
from schemas.sparse_dto import (SparseEmbedRequest, SparseEmbedResponse,)
from schemas.reranker_dto import (RerankRequest, RerankResponse)

import urllib3
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

class DenseModelInterface(ABC):
    @abstractmethod
    async def get_dense_embeddings(self, text: Union[str, List[str]]) -> DenseEmbedResponse:
        pass

class BaseDenseModel(DenseModelInterface):
    def __init__(self):
        self.url = str(os.getenv("DENSE_URL"))
        self.api_key = os.getenv("DENSE_API_KEY")
        self.model = os.getenv("DENSE_MODEL")
        self.mode_dim = int(os.getenv("DENSE_MODEL_DIM", 0))

    async def _make_call(self, url: str, payload: DenseEmbedRequest) -> DenseEmbedResponse:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=120.0,verify=False) as client:
            response = await client.post(url, json=payload.model_dump(exclude_none=True), headers=headers)
            logger.info(f"Raw Response from {url}: {response.text}")
            response.raise_for_status()
            return DenseEmbedResponse(**response.json())

class HostedDenseModel(BaseDenseModel):
    async def get_dense_embeddings(self, text: Union[str, List[str]]) -> DenseEmbedResponse:
        payload = DenseEmbedRequest(input=text, model=self.model)
        return await self._make_call(self.url, payload)

class LocalDenseModel(BaseDenseModel):
    async def get_dense_embeddings(self, text: Union[str, List[str]]) -> DenseEmbedResponse:
        target_url = f"{self.url.rstrip('/')}/text-embedding"
        payload = DenseEmbedRequest(input=text, dimension=self.mode_dim)
        return await self._make_call(target_url, payload)

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

class BaseSparseModel(SparseModelInterface):
    def __init__(self):
        self.url = str(os.getenv("SPARSE_URL"))
        self.api_key = os.getenv("SPARSE_API_KEY")
        self.model = os.getenv("SPARSE_MODEL")

    async def _make_call(self, url: str, payload: SparseEmbedRequest) -> SparseEmbedResponse:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=120.0,verify=False) as client:
            response = await client.post(url, json=payload.model_dump(exclude_none=True), headers=headers)
            logger.info(f"Raw Response from {url}: {response.text}")
            response.raise_for_status()
            return SparseEmbedResponse(**response.json())

class HostedSparseModel(BaseSparseModel):
    async def get_sparse_embeddings(self, text: Union[str, List[str]], top_k: int = 50) -> SparseEmbedResponse:
        payload = SparseEmbedRequest(input=text, model=self.model, top_k=top_k)
        return await self._make_call(self.url, payload)

class LocalSparseModel(BaseSparseModel):
    async def get_sparse_embeddings(self, text: Union[str, List[str]], top_k: int = 50) -> SparseEmbedResponse:
        target_url = f"{self.url.rstrip('/')}/sparse-text-embedding"
        payload = SparseEmbedRequest(input=text, top_k=top_k)
        return await self._make_call(target_url, payload)

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

class BaseReranker(RerankerInterface):
    def __init__(self):
        self.url = str(os.getenv("RERANKER_URL"))
        self.api_key = os.getenv("RERANKER_API_KEY")
        self.model = os.getenv("RERANKER_MODEL")

    async def _make_call(self, url: str, payload: RerankRequest) -> RerankResponse:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=120.0,verify=False) as client:
            response = await client.post(url, json=payload.model_dump(exclude_none=True), headers=headers)
            logger.info(f"Raw Response from {url}: {response.text}")
            response.raise_for_status()
            return RerankResponse(**response.json())

class HostedReranker(BaseReranker):
    async def rerank(self, query: str, documents: list, top_n: int = 5) -> RerankResponse:
        payload = RerankRequest(query=query, top_n=top_n, documents=documents, model=self.model, return_documents=True)
        return await self._make_call(self.url, payload)

class LocalReranker(BaseReranker):
    async def rerank(self, query: str, documents: list, top_n: int = 5) -> RerankResponse:
        target_url = f"{self.url.rstrip('/')}/text-cross-encoder"
        payload = RerankRequest(query=query, top_n=top_n, documents=documents, return_documents=True)
        return await self._make_call(target_url, payload)

class RerankerFactory:
    @staticmethod
    def get_instance() -> RerankerInterface:
        if os.getenv("RERANKER_HOSTED", "false").lower() == "true":
            return HostedReranker()
        return LocalReranker()