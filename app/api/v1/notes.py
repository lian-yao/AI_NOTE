"""
笔记 API（文件存储模式）。
"""
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.note import Note
from app.models.video import Video
from app.schemas.note import NoteCreate, NoteResponse

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("/", response_model=list[NoteResponse])
def list_notes(db: Session = Depends(get_db)):
    """获取笔记列表。"""
    return db.query(Note).order_by(Note.created_at.desc()).all()


@router.get("/{note_id}", response_model=NoteResponse)
def get_note(note_id: int, db: Session = Depends(get_db)):
    """获取单个笔记。"""
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="笔记不存在")
    return note


@router.get("/{video_id}/raw", response_class=PlainTextResponse)
def get_note_raw(video_id: str, db: Session = Depends(get_db)):
    """获取笔记的原始 Markdown 文本。"""
    note = db.query(Note).join(Note.video).filter(Video.video_id == video_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    try:
        return PlainTextResponse(content=Path(note.file_path).read_text(encoding="utf-8"), media_type="text/markdown")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="笔记文件未找到")


@router.post("/", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(data: NoteCreate, db: Session = Depends(get_db)):
    """创建笔记记录（内容由 NoteGenerator 写入文件）。"""
    note = Note(**data.model_dump())
    db.add(note)
    db.commit()
    db.refresh(note)
    return note
