from pydantic import BaseModel, Field
from typing import List, Union, Optional, Dict, Any


class DenseEmbedRequest(BaseModel):
    input: Union[str, List[str]]
    dimension: Optional[int] = None
    normalize: bool = False
    model:Optional[str] = None


class DenseEmbedding(BaseModel):
    index: int
    embedding: List[float]


class DenseEmbedResponse(BaseModel):
    dimension: int
    data: List[DenseEmbedding]
    usage: Dict[str, int]


class SparseEmbedRequest(BaseModel):
    input: Union[str, List[str]] = Field(..., description="Single string or list of strings to embed")
    top_k: Optional[int] = Field(None, description="Keep only top-k token weights. If None, return all non-zero weights.")
    model: Optional[str] = None


class SparseVector(BaseModel):
    indices: List[int]
    values: List[float]


class SparseEmbedding(BaseModel):
    index: int
    embedding: SparseVector


class SparseEmbedResponse(BaseModel):
    data: List[SparseEmbedding]
    usage: Dict[str, int]


class RerankDocument(BaseModel):
    content: str = Field(..., description="Document text to score against the query")


class RerankRequest(BaseModel):
    query: str
    documents: List[RerankDocument]
    top_n: int = Field(5)
    return_documents: bool = Field(True)
    model:Optional[str] = None


class RerankResult(BaseModel):
    index: int = Field(..., description="Original index of the document before reranking")
    rerank_score: float
    content: Optional[str] = Field(None, description="Document content, present only if return_documents=True")


class RerankResponse(BaseModel):
    top_n: int
    data: List[RerankResult]





