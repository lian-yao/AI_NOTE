"""
API v1 路由。
"""
from fastapi import APIRouter
from app.api.v1.notes import router as notes_router
from app.api.v1.pipeline import router as pipeline_router

router = APIRouter(prefix="/v1")
router.include_router(notes_router)
router.include_router(pipeline_router)
