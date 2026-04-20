from pydantic import BaseModel, Field
from typing import List, Union, Optional, Dict

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