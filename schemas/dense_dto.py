from pydantic import BaseModel, Field
from typing import List, Union, Optional, Dict


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