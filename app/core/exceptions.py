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


class AppError(Exception):
    """Generic application error with an explicit HTTP status code."""
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def register_exception_handlers(app: FastAPI) -> None:
    from fastapi.responses import JSONResponse as _JSONResponse  # noqa: PLC0415

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return _JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
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
