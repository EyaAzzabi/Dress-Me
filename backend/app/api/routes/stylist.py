import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.clothing_item import ClothingItem
from app.models.boutique_order import BoutiqueOrder
from app.models.stylist_recommendation import StylistRecommendation
from app.models.user import User
from app.schemas.clothing_item import ClothingItemRead

router = APIRouter(prefix="/stylist", tags=["stylist"])


def require_stylist(user: User) -> None:
    if user.role != "stylist":
        raise HTTPException(status_code=403, detail="Accès réservé aux conseillers.")


class ClientRead(BaseModel):
    id: uuid.UUID
    full_name: str | None = None
    email: str


class RecommendationCreate(BaseModel):
    customer_id: uuid.UUID
    item_ids: list[uuid.UUID]
    message: str | None = None


class RecommendationRead(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    item_ids: list[uuid.UUID]
    message: str | None = None
    created_at: datetime


class CustomerRecommendationRead(BaseModel):
    id: uuid.UUID
    stylist_id: uuid.UUID
    stylist_name: str | None = None
    items: list[ClothingItemRead]
    message: str | None = None
    created_at: datetime


class OrderCreate(BaseModel):
    item_id: uuid.UUID
    quantity: int = 1
    size: str | None = None
    customer_phone: str | None = None
    delivery_address: str | None = None
    note: str | None = None


class OrderRead(BaseModel):
    id: uuid.UUID
    stylist_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str | None = None
    customer_email: str | None = None
    item_id: uuid.UUID
    item_category: str | None = None
    item_image_url: str | None = None
    item_colors: list[str] | None = None
    item_price: float | None = None
    quantity: int
    size: str | None = None
    customer_phone: str | None = None
    delivery_address: str | None = None
    note: str | None = None
    status: str
    created_at: datetime


class BoutiqueCatalogRead(BaseModel):
    stylist_id: uuid.UUID
    stylist_name: str
    items: list[ClothingItemRead]


@router.get("/clients", response_model=list[ClientRead])
def list_clients(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_stylist(current_user)
    return db.query(User).filter(User.role == "customer").order_by(User.full_name.asc()).all()


@router.get("/recommendations", response_model=list[RecommendationRead])
def list_recommendations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_stylist(current_user)
    rows = db.query(StylistRecommendation).filter(StylistRecommendation.stylist_id == current_user.id).order_by(StylistRecommendation.created_at.desc()).all()
    return [
        RecommendationRead(
            id=row.id,
            customer_id=row.customer_id,
            item_ids=[uuid.UUID(value) for value in row.item_ids],
            message=row.message,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/recommendations", response_model=RecommendationRead)
def create_recommendation(payload: RecommendationCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_stylist(current_user)
    customer = db.get(User, payload.customer_id)
    if customer is None or customer.role != "customer":
        raise HTTPException(status_code=404, detail="Client introuvable.")
    if len(payload.item_ids) != 1:
        raise HTTPException(status_code=422, detail="Sélectionne exactement une pièce.")

    owned_ids = {
        row.id for row in db.query(ClothingItem.id).filter(
            ClothingItem.owner_id == current_user.id,
            ClothingItem.id.in_(payload.item_ids),
        ).all()
    }
    if owned_ids != set(payload.item_ids):
        raise HTTPException(status_code=422, detail="Certaines pièces ne font pas partie de ton stock.")

    row = StylistRecommendation(
        stylist_id=current_user.id,
        customer_id=payload.customer_id,
        item_ids=[str(value) for value in payload.item_ids],
        message=payload.message.strip() if payload.message else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return RecommendationRead(
        id=row.id,
        customer_id=row.customer_id,
        item_ids=[uuid.UUID(value) for value in row.item_ids],
        message=row.message,
        created_at=row.created_at,
    )


@router.get("/my-recommendations", response_model=list[CustomerRecommendationRead])
def customer_recommendations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Réservé aux clients DressMe.")

    rows = db.query(StylistRecommendation).filter(
        StylistRecommendation.customer_id == current_user.id
    ).order_by(StylistRecommendation.created_at.desc()).all()

    result = []
    for row in rows:
        ids = [uuid.UUID(value) for value in row.item_ids]
        items = db.query(ClothingItem).filter(ClothingItem.id.in_(ids)).all()
        items_by_id = {item.id: item for item in items}
        stylist = db.get(User, row.stylist_id)
        result.append(CustomerRecommendationRead(
            id=row.id,
            stylist_id=row.stylist_id,
            stylist_name=stylist.full_name if stylist else None,
            items=[items_by_id[item_id] for item_id in ids if item_id in items_by_id],
            message=row.message,
            created_at=row.created_at,
        ))
    return result


@router.get("/boutique-catalog", response_model=list[BoutiqueCatalogRead])
def boutique_catalog(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Réservé aux clients DressMe.")

    stylists = db.query(User).filter(User.role == "stylist").all()
    catalogs = []
    for stylist in stylists:
        items = db.query(ClothingItem).filter(
            ClothingItem.owner_id == stylist.id,
            ClothingItem.quantity > 0,
        ).order_by(ClothingItem.created_at.desc()).all()
        if items:
            catalogs.append(BoutiqueCatalogRead(
                stylist_id=stylist.id,
                stylist_name=(stylist.full_name or stylist.email).strip(),
                items=items,
            ))
    return catalogs


@router.post("/orders", response_model=OrderRead)
def create_order(payload: OrderCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "customer":
        raise HTTPException(status_code=403, detail="Réservé aux clients DressMe.")

    item = db.get(ClothingItem, payload.item_id)
    if item is None or (item.quantity or 0) <= 0:
        raise HTTPException(status_code=404, detail="Produit indisponible.")

    quantity = min(max(payload.quantity, 1), item.quantity or 1)
    if payload.size:
        available = (item.sizes or {}).get(payload.size, 0)
        if available <= 0:
            raise HTTPException(status_code=422, detail=f"La taille {payload.size} est indisponible.")
        quantity = min(quantity, available)

    order = BoutiqueOrder(
        customer_id=current_user.id,
        stylist_id=item.owner_id,
        item_id=item.id,
        quantity=quantity,
        size=payload.size,
        customer_phone=payload.customer_phone.strip() if payload.customer_phone else None,
        delivery_address=payload.delivery_address.strip() if payload.delivery_address else None,
        note=payload.note.strip() if payload.note else None,
    )
    db.add(order)

    item.quantity = max(0, (item.quantity or 0) - quantity)
    if payload.size:
        sizes = dict(item.sizes or {})
        sizes[payload.size] = max(0, sizes.get(payload.size, 0) - quantity)
        item.sizes = sizes

    db.commit()
    db.refresh(order)
    return OrderRead(
        id=order.id,
        stylist_id=order.stylist_id,
        customer_id=order.customer_id,
        customer_name=current_user.full_name,
        customer_email=current_user.email,
        item_id=order.item_id,
        item_category=item.category,
        item_image_url=item.image_url,
        item_colors=item.colors,
        item_price=item.price,
        quantity=order.quantity,
        size=order.size,
        customer_phone=order.customer_phone,
        delivery_address=order.delivery_address,
        note=order.note,
        status=order.status,
        created_at=order.created_at,
    )


@router.delete("/orders/{order_id}", status_code=204, response_class=Response)
def delete_order(order_id: uuid.UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_stylist(current_user)
    order = db.get(BoutiqueOrder, order_id)
    if order is None or order.stylist_id != current_user.id:
        raise HTTPException(status_code=404, detail="Commande introuvable.")

    item = db.get(ClothingItem, order.item_id)
    if item is not None:
        item.quantity = (item.quantity or 0) + order.quantity
        if order.size:
            sizes = dict(item.sizes or {})
            sizes[order.size] = sizes.get(order.size, 0) + order.quantity
            item.sizes = sizes

    db.delete(order)
    db.commit()
    return Response(status_code=204)


@router.get("/orders", response_model=list[OrderRead])
def list_orders(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_stylist(current_user)
    rows = db.query(BoutiqueOrder).filter(
        BoutiqueOrder.stylist_id == current_user.id
    ).order_by(BoutiqueOrder.created_at.desc()).all()
    result = []
    for order in rows:
        customer = db.get(User, order.customer_id)
        item = db.get(ClothingItem, order.item_id)
        result.append(OrderRead(
            id=order.id,
            stylist_id=order.stylist_id,
            customer_id=order.customer_id,
            customer_name=customer.full_name if customer else None,
            customer_email=customer.email if customer else None,
            item_id=order.item_id,
            item_category=item.category if item else None,
            item_image_url=item.image_url if item else None,
            item_colors=item.colors if item else None,
            item_price=item.price if item else None,
            quantity=order.quantity,
            size=order.size,
            customer_phone=order.customer_phone,
            delivery_address=order.delivery_address,
            note=order.note,
            status=order.status,
            created_at=order.created_at,
        ))
    return result
