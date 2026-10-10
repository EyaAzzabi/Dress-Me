import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents.vision_agent import VisionAgent
from app.api.deps import get_current_user
from app.db import vector_store
from app.db.session import get_db
from app.models.clothing_item import ClothingItem
from app.models.user import User
from app.schemas.clothing_item import ClothingItemCreate, ClothingItemRead
from app.services.storage import StorageService

router = APIRouter(prefix="/wardrobe", tags=["wardrobe"])
vision_agent = VisionAgent()
storage_service = StorageService()


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
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ClothingItem]:
    return (
        db.query(ClothingItem)
        .filter(ClothingItem.owner_id == current_user.id)
        .all()
    )


@router.post("/", response_model=ClothingItemRead, status_code=201)
def add_item(
    payload: ClothingItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClothingItem:
    attributes = vision_agent.run(image_url=payload.image_url)
    if attributes["category"] == "hors_perimetre":
        raise HTTPException(
            status_code=422,
            detail="This photo doesn't look like a clothing item — try a clearer photo of the item alone.",
        )

    item_id = uuid.uuid4()
    # The Pinecone vector id *is* the ClothingItem id — one less id to keep in sync.
    vector_store.upsert_item_embedding(
        item_id, attributes["embedding"], owner_id=current_user.id, category=attributes["category"]
    )
    item = ClothingItem(
        id=item_id,
        owner_id=current_user.id,
        image_url=payload.image_url,
        category=attributes["category"],
        colors=attributes["colors"],
        style=attributes["style"],
        season=payload.season,
        pattern=attributes["pattern"],
        embedding_id=str(item_id) if vector_store.is_configured() else None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=204)
def remove_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    item = (
        db.query(ClothingItem)
        .filter(ClothingItem.id == item_id, ClothingItem.owner_id == current_user.id)
        .first()
    )
    if item:
        vector_store.delete_item_embedding(item.id)
        db.delete(item)
        db.commit()
