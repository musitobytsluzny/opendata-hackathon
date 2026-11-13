from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DatasetQuery(BaseModel):
    query: str = Field(..., description="Search term or query for open datasets")
    category: Optional[str] = Field(None, description="Optional category filter")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")


class DatasetResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ActionRequest(BaseModel):
    action: str = Field(..., description="Action name to trigger in Central API")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Action payload parameters")
