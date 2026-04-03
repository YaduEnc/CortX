from fastapi import APIRouter

from app.api.v1.app import router as app_router
from app.api.v1.device import router as device_router
from app.api.v1.health import router as health_router
from app.api.v1.pairing import router as pairing_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(app_router)
api_router.include_router(device_router)
api_router.include_router(pairing_router)
