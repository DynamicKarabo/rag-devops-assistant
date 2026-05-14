"""
Pydantic models for the RAG API.
"""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Incoming query from user."""
    question: str = Field(..., min_length=1, max_length=2000, description="The DevOps question to answer")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of chunks to retrieve")
    include_sources: bool = Field(default=True, description="Return source citations")


class SourceCitation(BaseModel):
    """A source document cited in the answer."""
    url: str
    title: str
    snippet: str = Field(..., description="Relevant excerpt from the source")


class QueryResponse(BaseModel):
    """Response to a RAG query."""
    question: str
    answer: str
    sources: list[SourceCitation] = Field(default_factory=list)
    tokens_used: int = 0
    latency_ms: float = 0.0
    model: str = ""


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    qdrant_points: int = 0
    model_loaded: bool = False
    version: str = "0.1.0"
