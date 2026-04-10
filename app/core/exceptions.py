from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class TicketNotFoundError(Exception):
    def __init__(self, ticket_id: str):
        self.ticket_id = ticket_id
        super().__init__(f"Ticket not found: {ticket_id}")


class IngestionError(Exception):
    pass


class WebhookSignatureError(Exception):
    pass


class VectorStoreError(Exception):
    pass


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TicketNotFoundError)
    async def ticket_not_found_handler(request: Request, exc: TicketNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(IngestionError)
    async def ingestion_error_handler(request: Request, exc: IngestionError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(WebhookSignatureError)
    async def webhook_sig_handler(request: Request, exc: WebhookSignatureError):
        return JSONResponse(status_code=401, content={"detail": "Invalid webhook signature"})

    @app.exception_handler(Exception)
    async def generic_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
