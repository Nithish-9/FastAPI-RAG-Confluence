from pydantic import BaseModel, Field
from typing import List, Union, Optional, Dict,Any


class DenseEmbedRequest(BaseModel):
    input: Union[str, List[str]]
    dimension: Optional[int] = None
    normalize: bool = False
    model:Optional[str] = None


class DenseEmbedding(BaseModel):
    index: int
    embedding: List[float]


class DenseEmbedResponse(BaseModel):
    dimension: Optional[int] = None 
    data: List[DenseEmbedding]
    usage: Optional[Dict[str, Any]] = None 
