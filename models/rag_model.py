from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class RAGQueryRequest(BaseModel):
    query: str = Field(..., description="The natural language question or search term.")
    
    page_id: Optional[str] = Field(None, description="The specific Confluence Page ID to search within.")
    
    chunk_index: Optional[int] = Field(None, description="The sequential index of the chunk (e.g., 0, 1, 2) to retrieve a specific part of a document.")
    
    top_k: int = Field(5, description="Number of document chunks to return.")
    alpha: float = Field(0.5, description="Hybrid weight: 1.0 is pure semantic (Dense), 0.0 is pure keyword (Sparse).")
