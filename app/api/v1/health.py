from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/deep")
async def health_deep(request: Request):
    chroma = request.app.state.chroma
    try:
        await chroma.heartbeat()
        chroma_ok = True
    except Exception:
        chroma_ok = False
    return {"status": "ok" if chroma_ok else "degraded", "chroma": chroma_ok}
