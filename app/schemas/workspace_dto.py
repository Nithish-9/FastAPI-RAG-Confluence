from pydantic import BaseModel, Field
from typing import List, Optional

class CreateIndexRequest(BaseModel):
    content_id: str = Field(..., description="SHA-256 of file content, computed by Go client")
    workspace_id: str = Field(..., description="SHA-256 of workspace root absolute path")
    workspace_path: str = Field(...,description="Absolute path of workspace root on client")
    path: str = Field(..., description="Absolute file path on client machine")
    path_id: str = Field(..., description="SHA-256 of absolute file path")
    file_name: str = Field(..., description="e.g. LoanService.java")
    file_extension: str = Field(..., description="e.g. .java")


class DeleteIndexRequest(BaseModel):
    path_ids: List[str] = Field(..., description="Batch of path_ids to purge from the collection")


class WorkspaceRetrieveRequest(BaseModel):
    query: str = Field(..., description="Natural language or code search query from the LLM")
    top_k: int = Field(5, ge=1, le=20, description="Number of results to return after reranking")
    workspace_id: str = Field(..., description="Mandatory — scopes search to a single workspace")
    path_id: Optional[str] = Field(
        None,
        description=(
            "Optional — narrow search to a single file. "
            "LLM should pass this on follow-up calls once it knows the relevant file."
        ),
    )
    chunk_index: Optional[int] = Field(
        None,
        description=(
            "Optional — fetch a specific chunk by index. "
            "LLM should pass this when it wants to read more context around a previously returned chunk."
        ),
    )


class WorkspaceChunkResult(BaseModel):
    content: str
    file_name: str
    file_extension: str
    path: str
    path_id: str
    workspace_id: str
    chunk_index: int
    content_id: str
    symbol: Optional[str] = None      
    language: Optional[str] = None
    rrf_score: Optional[float] = None
    rerank_score: Optional[float] = None


class WorkspaceRetrieveResponse(BaseModel):
    status: str
    count: int
    data: List[WorkspaceChunkResult]
