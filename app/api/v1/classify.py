"""
POST /classify — synchronous fault classification endpoint.

Unlike ticket ingestion (202 + BackgroundTask), classification is fast enough
(~1–2 s) to return a complete result in a single request.

Request
-------
POST /api/v1/classify
Content-Type: application/json

{
  "text": "Base station BS-MUM-042 reporting -110 dBm RSSI. 3,200 subscribers
           affected in the Mumbai North sector. Antenna alignment nominal per NMS."
}

Response 200
------------
{
  "fault_type":          "signal_loss",
  "affected_layer":      "physical",
  "confidence_score":    0.91,
  "reasoning":           "RSSI well below threshold with antenna alignment confirmed
                          normal indicates a physical layer signal degradation fault.",
  "similar_ticket_ids":  ["TKT-A1B2C3D4", "TKT-E5F6G7H8", "TKT-I9J0K1L2"],
  "model":               "claude-sonnet-4-6",
  "latency_ms":          1340
}
"""
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.classifier.classifier import FaultClassifier, FaultClassifierError
from app.classifier.models import ClassificationRequest, ClassificationResult
from app.core.exceptions import AppError
from app.dependencies import get_fault_classifier

router = APIRouter(prefix="/classify", tags=["classify"])


@router.post(
    "/",
    response_model=ClassificationResult,
    status_code=status.HTTP_200_OK,
    summary="Classify a fault ticket",
    description=(
        "Classifies raw ticket text into a fault type and OSI layer using "
        "Claude's API, and returns up to 3 similar resolved historical ticket IDs "
        "retrieved by cosine similarity from the Chroma vector store."
    ),
)
async def classify_ticket(
    payload: ClassificationRequest,
    classifier: Annotated[FaultClassifier, Depends(get_fault_classifier)],
) -> ClassificationResult:
    try:
        return await classifier.classify(payload.text)
    except FaultClassifierError as exc:
        raise AppError(status_code=502, detail=str(exc)) from exc
