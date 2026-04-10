from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.core.exceptions import TicketNotFoundError
from app.dependencies import get_repo
from app.storage.repositories import TicketRepository

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/{ticket_id}")
async def get_recommendation(
    ticket_id: str,
    repo: Annotated[TicketRepository, Depends(get_repo)],
):
    row = await repo.get_ticket(ticket_id)
    if not row:
        raise TicketNotFoundError(ticket_id)

    rec = await repo.get_recommendation(ticket_id)
    if rec is None:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"ticket_id": ticket_id, "status": row.status, "message": "Processing in progress"},
        )

    return rec
