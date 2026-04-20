from pydantic import BaseModel, Field
from typing import List, Optional

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