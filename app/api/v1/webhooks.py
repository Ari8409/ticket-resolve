from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, status

from app.config import Settings, get_settings
from app.core.exceptions import WebhookSignatureError
from app.dependencies import get_matching_engine, get_repo, get_resolution_agent, get_sop_retriever
from app.ingestion.webhook_ingester import WebhookIngester
from app.matching.engine import MatchingEngine
from app.recommendation.agent import ResolutionAgent
from app.sop.retriever import SOPRetriever
from app.storage.repositories import TicketRepository
from app.tasks.background import run_resolution_pipeline

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/{source}", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    source: str,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[TicketRepository, Depends(get_repo)],
    matching_engine: Annotated[MatchingEngine, Depends(get_matching_engine)],
    sop_retriever: Annotated[SOPRetriever, Depends(get_sop_retriever)],
    agent: Annotated[ResolutionAgent, Depends(get_resolution_agent)],
    x_hub_signature_256: str = Header(default=""),
):
    body = await request.body()
    ingester = WebhookIngester(secret=settings.WEBHOOK_SECRET)

    if x_hub_signature_256:
        if not ingester.verify_signature(body, x_hub_signature_256):
            raise WebhookSignatureError()

    payload = await request.json()
    ticket = await ingester.ingest(payload)
    ticket_id = await repo.save(ticket)

    background_tasks.add_task(
        run_resolution_pipeline,
        ticket_id=ticket_id,
        ticket=ticket,
        matching_engine=matching_engine,
        sop_retriever=sop_retriever,
        agent=agent,
        repo=repo,
    )

    return {"ticket_id": ticket_id, "source": source, "status": "accepted"}
