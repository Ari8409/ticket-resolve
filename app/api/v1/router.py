from fastapi import APIRouter

from app.api.v1 import classify, health, recommendations, review, tickets, upload, webhooks

v1_router = APIRouter()

v1_router.include_router(health.router)
v1_router.include_router(tickets.router)
v1_router.include_router(upload.router)
v1_router.include_router(recommendations.router)
v1_router.include_router(review.router)
v1_router.include_router(webhooks.router)
v1_router.include_router(classify.router)
