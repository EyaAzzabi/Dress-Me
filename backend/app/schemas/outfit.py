import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OutfitRequest(BaseModel):
    occasion: str | None = None
    weather: str | None = None
    season: str | None = None
    city: str | None = None  # looked up via WeatherService when weather isn't given directly


class OutfitRead(BaseModel):
    id: uuid.UUID
    item_ids: list[uuid.UUID]
    occasion: str | None = None
    relevance_score: float | None = None
    explanation: str | None = None

    class Config:
        from_attributes = True


class OutfitRecommendationResult(BaseModel):
    context: dict
    outfits: list[OutfitRead]


GarmentCategory = Literal["haut", "bas", "robe", "veste", "chaussures", "sac", "accessoire"]


class PurchaseCheckRequest(BaseModel):
    image_url: str
    price: float | None = Field(default=None, gt=0)  # TND, as seen in the shop
    category: GarmentCategory | None = None  # from /purchase/extract, overrides the classifier


class GarmentExtractionRequest(BaseModel):
    image_url: str


class ExtractedGarment(BaseModel):
    category: str  # DressMe category, or hors_perimetre for a non-clothing photo
    color: str | None = None
    image_url: str  # the cut-out on a white background (or the photo itself, see person_detected)
    share: float  # share of the person this garment covers


class GarmentExtractionResult(BaseModel):
    person_detected: bool  # False: no one wearing clothes, the whole photo is the single item
    garments: list[ExtractedGarment]


class PurchaseItemSummary(BaseModel):
    category: str
    color: str | None = None
    pattern: str | None = None
    style: str | None = None


class PurchaseFactor(BaseModel):
    key: str  # versatility | uniqueness | style_fit | price
    label: str
    score: float  # 0-1
    weight: float  # renormalized over the factors actually present
    detail: str


class WardrobeItemRef(BaseModel):
    id: uuid.UUID
    image_url: str
    category: str | None = None


class DuplicateItem(WardrobeItemRef):
    similarity: float


class UnlockedOutfit(BaseModel):
    items: list[WardrobeItemRef]  # existing pieces worn with the candidate
    score: float  # mean pairwise compatibility (Polyvore model)


class PriceInsight(BaseModel):
    price: float | None = None
    market_median: float
    market_min: float
    market_max: float
    sample_size: int
    percentile: float | None = None  # share of similar products cheaper than `price`
    label: str | None = None  # bon_prix | prix_marche | cher


class CatalogAlternative(BaseModel):
    item_key: str | None = None
    name: str
    brand: str | None = None
    category: str | None = None
    price: float | str | None = None
    image_url: str | None = None
    similarity: float | None = None  # FashionCLIP cosine similarity to the candidate
    cheaper: bool | None = None
    product_url: str | None = None  # the product's page on the brand's site
    store_url: str | None = None  # the brand's site
    buyable: bool = False  # live sizes/stock and checkout available (/purchase/products/...)


class CostPerWear(BaseModel):
    wears_per_year: int
    cost_per_wear: float  # TND
    label: str  # excellent | correct | eleve


class BrandRecommendation(BaseModel):
    name: str
    website: str | None = None
    affinity: float  # mean FashionCLIP similarity of the brand's closest products
    product_count: int  # products of this category in the brand's catalog
    price_min: float | None = None
    price_max: float | None = None
    showcase: list[CatalogAlternative] = []


class PurchaseCheckResult(BaseModel):
    verdict: str  # recommended | think_twice | not_recommended
    score: int  # 0-100
    compatibility_score: float  # score / 100, kept for older clients
    explanation: str
    item: PurchaseItemSummary
    factors: list[PurchaseFactor] = []
    outfits_unlocked: int = 0
    outfit_examples: list[UnlockedOutfit] = []
    duplicates: list[DuplicateItem] = []
    similar_item_ids: list[uuid.UUID] = []
    price_insight: PriceInsight | None = None
    cost_per_wear: CostPerWear | None = None
    catalog_alternatives: list[CatalogAlternative] = []
    tunisian_brands: list[BrandRecommendation] = []


class ProductVariant(BaseModel):
    id: int
    title: str | None = None  # size / colour, None for single-variant products
    available: bool
    price: float | None = None
    checkout_url: str  # the brand's checkout with this variant in the cart


class LiveProduct(BaseModel):
    title: str
    brand: str
    product_url: str
    store_url: str
    image_url: str | None = None
    price: float | None = None
    compare_at_price: float | None = None  # pre-sale price when the product is on sale
    available: bool
    variants: list[ProductVariant]


class PurchaseHistoryItem(BaseModel):
    id: uuid.UUID
    image_url: str
    category: str
    color: str | None = None
    price: float | None = None
    verdict: str
    score: int
    result: PurchaseCheckResult  # the check exactly as it was shown
    created_at: datetime

    class Config:
        from_attributes = True


class WishlistAddRequest(BaseModel):
    item_key: str = Field(min_length=1, max_length=255)


class WishlistEntry(BaseModel):
    item_key: str
    name: str
    brand: str | None = None
    category: str | None = None
    image_url: str | None = None
    saved_price: float | None = None
    live_price: float | None = None  # None when the store couldn't be reached
    available: bool | None = None
    price_drop: float | None = None  # TND saved since the product was added
    product_url: str | None = None
    store_url: str | None = None
    buyable: bool = False
    created_at: datetime
