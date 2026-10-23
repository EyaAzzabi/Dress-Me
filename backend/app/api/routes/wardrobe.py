import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.agents.llm_agent import LLMConfigurationError
from app.agents.metadata_agent import MetadataAgent
from app.agents.vision_agent import VisionAgent
from app.agents.wardrobe_ingestion_agent import WardrobeIngestionAgent
from app.agents.workflow_service import AgentWorkflowService
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.clothing_item import ClothingItem
from app.models.user import User
from app.schemas.clothing_item import (
    ClothingItemCreate,
    ClothingItemRead,
    ClothingItemUpdate,
    ItemUsage,
    WardrobeAnalysisPayload,
    WardrobeAnalysisResponse,
    WornPayload,
)
from app.services.storage import StorageService

router = APIRouter(prefix="/wardrobe", tags=["wardrobe"])
storage_service = StorageService()
vision_agent = VisionAgent()


@router.post("/analyze", response_model=WardrobeAnalysisResponse)
def analyze_photo(
    payload: WardrobeAnalysisPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Multimodal analysis: Computer Vision (OpenCV blur & quality), K-Means color palette,
    FashionCLIP ViT-B/32 multimodal zero-shot classification, RAG duplicate check and outfit pairing."""
    agent = WardrobeIngestionAgent(db=db, vision_agent=vision_agent)
    try:
        results = agent.run(image_url=payload.image_url, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return results


@router.post("/upload")
async def upload_photo(
    file: UploadFile, current_user: User = Depends(get_current_user)
) -> dict:
    """Turns a raw photo into a hosted image_url, for clients that don't already have
    one — the actual wardrobe item is then created via POST /wardrobe/ with that URL,
    which is what runs the Vision Agent."""
    if not storage_service.is_configured():
        raise HTTPException(
            status_code=503, detail="Image storage isn't configured on this server."
        )
    content = await file.read()
    content_type = file.content_type or "application/octet-stream"
    image_url = storage_service.upload_image(content, content_type)
    return {"image_url": image_url}


@router.get("/", response_model=list[ClothingItemRead])
def list_items(
    category: str | None = None,
    season: str | None = None,
    style: str | None = None,
    color: str | None = None,
    q: str | None = Query(None, description="Free-text search over category/style/season/pattern/colors"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ClothingItem]:
    return MetadataAgent(db).run(
        user_id=current_user.id, category=category, season=season, style=style, color=color, query=q
    )["items"]


@router.get("/usage", response_model=list[ItemUsage])
def item_usage(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[dict]:
    """How often / how recently each item appears in the owner's planned outfits."""
    history = MetadataAgent(db).usage_history(user_id=current_user.id)
    return [{"item_id": item_id, **entry} for item_id, entry in history.items()]


@router.post("/", response_model=ClothingItemRead, status_code=201)
def add_item(
    payload: ClothingItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClothingItem:
    try:
        return AgentWorkflowService(db).add_wardrobe_item(
            user_id=current_user.id,
            image_url=payload.image_url,
            season=payload.season,
            category=payload.category,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=getattr(exc, "detail", str(exc))) from exc


@router.patch("/{item_id}", response_model=ClothingItemRead)
def update_item(
    item_id: uuid.UUID,
    payload: ClothingItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClothingItem:
    item = MetadataAgent(db).update_item(
        user_id=current_user.id,
        item_id=item_id,
        changes=payload.model_dump(exclude_unset=True, exclude_none=True),
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    return item


@router.post("/{item_id}/worn", response_model=ItemUsage)
def mark_worn(
    item_id: uuid.UUID,
    payload: WornPayload | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """"Je l'ai porté": records the item as worn on a day (default today)."""
    agent = MetadataAgent(db)
    day = payload.day if payload else None
    if day is not None and day > date.today():
        raise HTTPException(status_code=422, detail="You can't mark an item as worn in the future.")
    if not agent.log_worn(user_id=current_user.id, item_id=item_id, day=day):
        raise HTTPException(status_code=404, detail="Item not found.")
    return {"item_id": item_id, **agent.usage_history(user_id=current_user.id)[item_id]}


@router.delete("/{item_id}", status_code=204)
def remove_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    MetadataAgent(db).remove_item(user_id=current_user.id, item_id=item_id)
