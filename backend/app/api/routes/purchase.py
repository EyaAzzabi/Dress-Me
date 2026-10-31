import copy
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents.orchestrator import AgentOrchestrator
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.purchase_history import PurchaseHistoryEntry
from app.models.user import User
from app.models.wishlist_item import WishlistItem
from app.schemas.outfit import (
    GarmentExtractionRequest,
    GarmentExtractionResult,
    LiveProduct,
    PurchaseCheckRequest,
    PurchaseCheckResult,
    PurchaseHistoryItem,
    WishlistAddRequest,
    WishlistEntry,
)
from app.services import store_checkout, tunisian_brands
from app.services.catalog_index import CatalogIndex
from app.services.storage import StorageService

router = APIRouter(prefix="/purchase", tags=["purchase"])


@router.post("/extract", response_model=GarmentExtractionResult)
def extract_garments(
    payload: GarmentExtractionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Splits a photo into its individual garments, each with its own image_url to
    pass to /purchase/check."""
    if not StorageService().is_configured():
        raise HTTPException(status_code=503, detail="Image storage isn't configured on this server.")
    return AgentOrchestrator(db).extract_garments(image_url=payload.image_url)


@router.post("/check", response_model=PurchaseCheckResult)
def check_purchase(
    payload: PurchaseCheckRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    orchestrator = AgentOrchestrator(db)
    result = orchestrator.evaluate_purchase(
        user_id=current_user.id, image_url=payload.image_url, price=payload.price,
        category=payload.category,
    )
    if result["item"]["category"] != "hors_perimetre":
        result = PurchaseCheckResult(**result).model_dump(mode="json")
        db.add(PurchaseHistoryEntry(
            owner_id=current_user.id, image_url=payload.image_url, category=result["item"]["category"],
            color=result["item"]["color"], price=payload.price, verdict=result["verdict"],
            score=result["score"], result=result,
        ))
        db.commit()
    return result


@router.get("/history", response_model=list[PurchaseHistoryItem])
def list_history(
    limit: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PurchaseHistoryItem]:
    entries = db.scalars(
        select(PurchaseHistoryEntry)
        .where(PurchaseHistoryEntry.owner_id == current_user.id)
        .order_by(PurchaseHistoryEntry.created_at.desc())
        .limit(limit)
    ).all()
    items = []
    for entry in entries:
        result = copy.deepcopy(entry.result)
        _refresh_links(result)
        items.append(PurchaseHistoryItem(
            id=entry.id, image_url=entry.image_url, category=entry.category, color=entry.color,
            price=entry.price, verdict=entry.verdict, score=entry.score, result=result,
            created_at=entry.created_at,
        ))
    return items


@router.delete("/history/{entry_id}", status_code=204)
def delete_history_entry(
    entry_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    db.execute(delete(PurchaseHistoryEntry).where(
        PurchaseHistoryEntry.id == entry_id, PurchaseHistoryEntry.owner_id == current_user.id))
    db.commit()


@router.delete("/history", status_code=204)
def clear_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    db.execute(delete(PurchaseHistoryEntry).where(PurchaseHistoryEntry.owner_id == current_user.id))
    db.commit()


@router.get("/products/{item_key}/live", response_model=LiveProduct)
def live_product(item_key: str, current_user: User = Depends(get_current_user)) -> dict:
    """Current price, sizes and stock on the brand's store, each size with a link to
    the store's checkout — where the payment happens."""
    try:
        return store_checkout.live_product(item_key)
    except store_checkout.ProductUnavailable:
        raise HTTPException(status_code=404, detail="Produit indisponible sur le site de la marque.")


@router.get("/wishlist", response_model=list[WishlistEntry])
def list_wishlist(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    items = db.scalars(
        select(WishlistItem).where(WishlistItem.owner_id == current_user.id).order_by(WishlistItem.created_at.desc())
    ).all()
    live = store_checkout.live_prices([i.item_key for i in items if tunisian_brands.links(i.item_key, i.brand)["buyable"]])
    return [_wishlist_entry(item, live.get(item.item_key)) for item in items]


@router.post("/wishlist", response_model=WishlistEntry, status_code=201)
def add_to_wishlist(
    payload: WishlistAddRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    product = CatalogIndex().get(payload.item_key)
    if product is None:
        raise HTTPException(status_code=404, detail="Produit inconnu du catalogue.")
    item = db.scalar(select(WishlistItem).where(
        WishlistItem.owner_id == current_user.id, WishlistItem.item_key == product.item_key))
    if item is None:
        item = WishlistItem(
            owner_id=current_user.id, item_key=product.item_key, name=product.name, brand=product.brand,
            category=product.category, image_url=product.image_url, saved_price=product.price,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
    return _wishlist_entry(item, None)


@router.delete("/wishlist/{item_key}", status_code=204)
def remove_from_wishlist(
    item_key: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    item = db.scalar(select(WishlistItem).where(
        WishlistItem.owner_id == current_user.id, WishlistItem.item_key == item_key))
    if item is not None:
        db.delete(item)
        db.commit()


def _refresh_links(result: dict | None) -> None:
    """Product links are derived from item_key, so a saved analysis is re-linked
    with the current rules instead of keeping the links it was saved with."""
    if not result:
        return
    products = list(result.get("catalog_alternatives") or [])
    for brand in result.get("tunisian_brands") or []:
        products += brand.get("showcase") or []
    for product in products:
        if product.get("item_key"):
            product.update(tunisian_brands.links(product["item_key"], product.get("brand")))


def _wishlist_entry(item: WishlistItem, live: dict | None) -> dict:
    live_price = live["price"] if live else None
    drop = None
    if live_price is not None and item.saved_price is not None and live_price < item.saved_price:
        drop = round(item.saved_price - live_price, 2)
    return {
        "item_key": item.item_key, "name": item.name, "brand": item.brand, "category": item.category,
        "image_url": item.image_url, "saved_price": item.saved_price, "live_price": live_price,
        "available": live["available"] if live else None, "price_drop": drop,
        "created_at": item.created_at, **tunisian_brands.links(item.item_key, item.brand),
    }
