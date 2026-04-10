from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.dependencies import get_matching_engine, get_repo, get_resolution_agent, get_sop_retriever
from app.matching.engine import MatchingEngine
from app.models.ticket import TicketIn, TicketOut
from app.recommendation.agent import ResolutionAgent
from app.sop.retriever import SOPRetriever
from app.storage.repositories import TicketRepository
from app.tasks.background import run_resolution_pipeline

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("/", response_model=TicketOut, status_code=status.HTTP_202_ACCEPTED)
async def ingest_ticket(
    payload: TicketIn,
    background_tasks: BackgroundTasks,
    repo: Annotated[TicketRepository, Depends(get_repo)],
    matching_engine: Annotated[MatchingEngine, Depends(get_matching_engine)],
    sop_retriever: Annotated[SOPRetriever, Depends(get_sop_retriever)],
    agent: Annotated[ResolutionAgent, Depends(get_resolution_agent)],
):
    ticket_id = await repo.save(payload)

    background_tasks.add_task(
        run_resolution_pipeline,
        ticket_id=ticket_id,
        ticket=payload,
        matching_engine=matching_engine,
        sop_retriever=sop_retriever,
        agent=agent,
        repo=repo,
    )

    return TicketOut(
        ticket_id=ticket_id,
        status="pending",
        created_at=payload.created_at,
        recommendation_ready=False,
    )


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: str,
    repo: Annotated[TicketRepository, Depends(get_repo)],
):
    from app.core.exceptions import TicketNotFoundError

    row = await repo.get_ticket(ticket_id)
    if not row:
        raise TicketNotFoundError(ticket_id)

    rec = await repo.get_recommendation(ticket_id)
    return TicketOut(
        ticket_id=row.ticket_id,
        status=row.status,
        created_at=row.created_at,
        recommendation_ready=rec is not None,
    )
