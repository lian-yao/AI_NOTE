"""
Enabled model management API.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.model_usage import clear_model_usage_for_model
from app.core.provider_store import (
    enabled_model_to_dict,
    seed_default_enabled_models,
    seed_default_providers,
)
from app.models.provider import EnabledModel, LLMProvider
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/models", tags=["models"])


class CreateModelRequest(BaseModel):
    provider_id: str
    model_name: str


def _ensure_default_enabled_models(db: Session) -> None:
    if seed_default_enabled_models(db):
        db.commit()


@router.get("")
async def list_models(
    provider_id: Optional[str] = None,
    enabled: bool = True,
    include_disabled: bool = False,
    db: Session = Depends(get_db),
):
    """List persisted models, optionally including disabled rows."""
    _ensure_default_enabled_models(db)

    query = db.query(EnabledModel)
    if provider_id:
        query = query.filter(EnabledModel.provider_id == provider_id)
    if not include_disabled:
        query = query.filter(EnabledModel.enabled == enabled)
    models = query.order_by(EnabledModel.created_at.asc(), EnabledModel.id.asc()).all()
    return ApiResponse(data={"items": [enabled_model_to_dict(model) for model in models]})


@router.post("")
async def enable_model(req: CreateModelRequest, db: Session = Depends(get_db)):
    """Enable a model for a provider."""
    provider_id = req.provider_id.strip()
    model_name = req.model_name.strip()
    if not provider_id or not model_name:
        raise HTTPException(400, "provider_id and model_name are required")

    if seed_default_providers(db):
        db.commit()

    provider = db.get(LLMProvider, provider_id)
    if not provider:
        raise HTTPException(404, "Provider not found")

    model = (
        db.query(EnabledModel)
        .filter(
            EnabledModel.provider_id == provider_id,
            EnabledModel.model_name == model_name,
        )
        .first()
    )
    if model:
        if not model.enabled:
            model.enabled = True
            db.commit()
            db.refresh(model)
        return ApiResponse(data=enabled_model_to_dict(model))

    model = EnabledModel(provider_id=provider_id, model_name=model_name, enabled=True)
    db.add(model)
    db.commit()
    db.refresh(model)
    return ApiResponse(data=enabled_model_to_dict(model))


@router.delete("/{model_id:int}")
async def delete_model(model_id: int, db: Session = Depends(get_db)):
    """Disable a model while keeping the row for persistence."""
    model = db.get(EnabledModel, model_id)
    if not model:
        raise HTTPException(404, "Model not found")

    model.enabled = False
    clear_model_usage_for_model(model.provider_id, model.model_name)
    db.commit()
    return ApiResponse(data={"deleted": True})
