"""
\u5df2\u542f\u7528\u6a21\u578b\u7ba1\u7406\uff08\u6570\u636e\u5e93\u6301\u4e45\u5316\uff09
\u5185\u7f6e Provider \u7684\u6a21\u578b\u548c\u81ea\u5b9a\u4e49 Provider \u7684\u6a21\u578b\u5747\u5b58\u5165 enabled_models \u8868\u3002
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enabled_model import EnabledModel
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/models", tags=["models"])


class CreateModelRequest(BaseModel):
    provider_id: str
    model_name: str


@router.get("")
async def list_models(provider_id: Optional[str] = None, enabled: bool = True, db: Session = Depends(get_db)):
    """\u83b7\u53d6\u5df2\u542f\u7528\u6a21\u578b\u5217\u8868"""
    q = db.query(EnabledModel).filter(EnabledModel.enabled == True)
    if provider_id:
        q = q.filter(EnabledModel.provider_id == provider_id)
    items = q.all()
    return ApiResponse(data={"items": [{
        "id": m.id,
        "provider_id": m.provider_id,
        "model_name": m.model_name,
        "enabled": m.enabled,
        "created_at": str(m.created_at),
    } for m in items]})


@router.post("")
async def enable_model(req: CreateModelRequest, db: Session = Depends(get_db)):
    """\u542f\u7528\u4e00\u4e2a\u6a21\u578b"""
    # \u68c0\u67e5\u662f\u5426\u5df2\u5b58\u5728
    existing = db.query(EnabledModel).filter(
        EnabledModel.provider_id == req.provider_id,
        EnabledModel.model_name == req.model_name,
    ).first()
    if existing:
        existing.enabled = True
        db.commit()
        return ApiResponse(data={"id": existing.id, "provider_id": existing.provider_id, "model_name": existing.model_name})
    # \u65b0\u589e
    m = EnabledModel(provider_id=req.provider_id, model_name=req.model_name, enabled=True)
    db.add(m)
    db.commit()
    return ApiResponse(data={"id": m.id, "provider_id": m.provider_id, "model_name": m.model_name})


@router.delete("/{model_id:int}")
async def delete_model(model_id: int, db: Session = Depends(get_db)):
    """\u5220\u9664\u6a21\u578b"""
    m = db.query(EnabledModel).filter(EnabledModel.id == model_id).first()
    if not m:
        raise HTTPException(404, "Model not found")
    db.delete(m)
    db.commit()
    return ApiResponse(data={"deleted": True})
