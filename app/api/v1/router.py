from fastapi import APIRouter

from app.api.v1 import chat, classify, health, locations, network, recommendations, review, sla, stats, tickets, triage, upload, webhooks

v1_router = APIRouter()

v1_router.include_router(health.router)
v1_router.include_router(tickets.router)
v1_router.include_router(upload.router)
v1_router.include_router(recommendations.router)
v1_router.include_router(review.router)
# Human-in-the-loop triage endpoints (PENDING_REVIEW queue, assign, manual-resolve)
v1_router.include_router(triage.router)
v1_router.include_router(webhooks.router)
v1_router.include_router(classify.router)
# SLA tracking — targets table + compliance summary (R-15)
v1_router.include_router(sla.router)
# Dashboard stats + paginated ticket list
v1_router.include_router(stats.router)
# Location geocoding summary (must be after stats to avoid path shadowing)
v1_router.include_router(locations.router)
# Cognitive chat interface for NOC engineers
v1_router.include_router(chat.router)
# Network topology graph
v1_router.include_router(network.router)
