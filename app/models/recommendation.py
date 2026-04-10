from typing import Optional

from pydantic import BaseModel, Field


class SimilarTicket(BaseModel):
    ticket_id: str
    title: str
    score: float
    resolution_summary: Optional[str] = None


class RankedSOP(BaseModel):
    """
    A Standard Operating Procedure ranked by relevance to a specific ticket.
    Produced by the recommendation agent after retrieving and scoring candidates.
    """
    sop_id:           str
    title:            str
    confidence_score: float = Field(ge=0.0, le=1.0, description="Relevance confidence 0–1")
    summary:          str   = Field(default="", description="One-sentence abstract of what the SOP resolves")
    match_reason:     str   = Field(default="", description="Why this SOP was ranked at this position")
    on_site_required: bool  = False


class TicketEmbeddingResult(BaseModel):
    """
    Output of TicketEmbeddingPipeline.run().

    Carries the raw embedding vector alongside the top-k resolved
    similar tickets retrieved from Chroma by cosine similarity.
    """
    ticket_id:      str
    description:    str
    embedding:      list[float]             # raw float vector (embedding_dim values)
    embedding_dim:  int                     # length of embedding vector
    model_name:     str                     # sentence-transformers model used
    top_matches:    list[SimilarTicket]     # resolved tickets ranked by cosine similarity


class SOPMatch(BaseModel):
    sop_id: str
    title: str
    content: str
    score: float
    doc_path: Optional[str] = None


class RecommendationResult(BaseModel):
    ticket_id: str
    recommended_steps: list[str] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)
    relevant_sops: list[str] = Field(default_factory=list)
    similar_ticket_ids: list[str] = Field(default_factory=list)
    escalation_required: bool = False
    reasoning: str = ""
    similar_tickets: list[SimilarTicket] = Field(default_factory=list)
    sop_matches: list[SOPMatch] = Field(default_factory=list)
