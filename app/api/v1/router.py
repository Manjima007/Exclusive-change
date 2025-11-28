"""
API v1 Router.

This module combines all v1 endpoint routers into a single router
that can be mounted on the main FastAPI application.
"""

from fastapi import APIRouter

from app.api.v1.endpoints.api_keys import router as api_keys_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.environments import router as environments_router
from app.api.v1.endpoints.evaluate import config_router, router as evaluate_router
from app.api.v1.endpoints.flags import router as flags_router
from app.api.v1.endpoints.tenants import router as tenants_router

# Create the main v1 router
api_router = APIRouter(prefix="/api/v1")

# Include all endpoint routers
# Authentication (no auth required)
api_router.include_router(auth_router)

# Management API (JWT Auth required)
api_router.include_router(tenants_router)
api_router.include_router(flags_router)
api_router.include_router(environments_router)
api_router.include_router(api_keys_router)

# Evaluation API (API Key Auth required)
api_router.include_router(evaluate_router)
api_router.include_router(config_router)  # /flags/config endpoint
