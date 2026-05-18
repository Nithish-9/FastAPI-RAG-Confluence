from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class DeleteIndexRequest(BaseModel):
    page_ids: list[str] = Field(..., description="List of page_ids to delete from the index")


class EnterpriseRetrieveRequest(BaseModel):
    query: str = Field(..., description="Search query text")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of results to return")
    page_id: Optional[str] = Field(default=None, description="Filter results to a specific page_id")
    chunk_index: Optional[int] = Field(default=None, description="Filter results to a specific chunk index")