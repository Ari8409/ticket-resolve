from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status

from app.config import Settings, get_settings
from app.dependencies import get_matching_engine, get_repo, get_resolution_agent, get_sop_retriever
from app.ingestion.file_ingester import FileIngester
from app.matching.engine import MatchingEngine
from app.recommendation.agent import ResolutionAgent
from app.sop.retriever import SOPRetriever
from app.storage.repositories import TicketRepository
from app.tasks.background import run_resolution_pipeline

router = APIRouter(prefix="/tickets", tags=["tickets"])
_ingester = FileIngester()


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_tickets(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    repo: Annotated[TicketRepository, Depends(get_repo)],
    matching_engine: Annotated[MatchingEngine, Depends(get_matching_engine)],
    sop_retriever: Annotated[SOPRetriever, Depends(get_sop_retriever)],
    agent: Annotated[ResolutionAgent, Depends(get_resolution_agent)],
):
    if file.size and file.size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")

    content = await file.read()
    filename = file.filename or "upload.csv"

    ticket_ids: list[str] = []
    async for ticket in _ingester.ingest_bytes(content, filename):
        ticket_id = await repo.save(ticket)
        ticket_ids.append(ticket_id)
        background_tasks.add_task(
            run_resolution_pipeline,
            ticket_id=ticket_id,
            ticket=ticket,
            matching_engine=matching_engine,
            sop_retriever=sop_retriever,
            agent=agent,
            repo=repo,
        )

    return {"accepted": len(ticket_ids), "ticket_ids": ticket_ids}
