"""
API v1 路由。
"""
from fastapi import APIRouter
from app.api.v1.notes import router as notes_router
from app.api.v1.pipeline import router as pipeline_router
from app.api.v1.system import router as system_router
from app.api.v1.videos import router as videos_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.frontend import router as frontend_router
from app.api.v1.ws import router as ws_router
from app.api.v1.qa import router as qa_router
from app.api.v1.providers import router as providers_router
from app.api.v1.transcribers import router as transcribers_router
from app.api.v1.network import router as network_router
from app.api.v1.platforms import router as platforms_router
from app.api.v1.models import router as models_router

from app.api.v1.platforms import router as platforms_router
from app.api.v1.providers import router as providers_router
from app.api.v1.models import router as models_router

router = APIRouter(prefix="/v1")
router.include_router(notes_router)
router.include_router(pipeline_router)
router.include_router(system_router)
router.include_router(videos_router)
router.include_router(tasks_router)
router.include_router(ws_router)
router.include_router(frontend_router)
router.include_router(qa_router)
router.include_router(providers_router)
router.include_router(transcribers_router)
router.include_router(network_router)
router.include_router(platforms_router)
router.include_router(models_router)

router.include_router(platforms_router)
router.include_router(providers_router)
router.include_router(models_router)