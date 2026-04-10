from typing import Optional

from pydantic import BaseModel


class SOPDocument(BaseModel):
    sop_id: str
    title: str
    content: str
    category: Optional[str] = None
    doc_path: Optional[str] = None
    tags: list[str] = []


class SOPChunk(BaseModel):
    chunk_id: str
    sop_id: str
    title: str
    content: str
    chunk_index: int
    doc_path: Optional[str] = None
    category: Optional[str] = None
