import uuid

from pydantic import BaseModel


class AvatarSet(BaseModel):
    image_url: str


class TryOnRequest(BaseModel):
    garment_item_id: uuid.UUID


class TryOnResult(BaseModel):
    result_image_url: str
