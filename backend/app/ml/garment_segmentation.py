"""Clothing segmentation: finds each garment worn in a photo and cuts it out.

Backed by SegFormer-B2 fine-tuned for human parsing on the ATR dataset
(mattmdjaga/segformer_b2_clothes): a per-pixel label among 18 classes (upper clothes,
pants, skirt, dress, shoes, bag, hat, belt, scarf, sunglasses — plus hair, face,
arms, legs and background). Each garment is cut out along its mask and pasted on a
white background, which is how catalog product photos look — so the cut-out embeds
the same way with FashionCLIP as the products the agents were calibrated on.

Trained on photos of people: on a flat product photo (no one wearing it) the labels
are unreliable, so callers should fall back to the whole image when
`person_detected` is False.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

SEGFORMER_REPO = "mattmdjaga/segformer_b2_clothes"
INPUT_SIZE = 512
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# ATR label ids -> DressMe category. Left/right shoe are merged into one item.
GARMENT_LABELS = {
    4: "haut",  # Upper-clothes (tops and jackets alike — told apart afterwards)
    5: "bas",  # Skirt
    6: "bas",  # Pants
    7: "robe",  # Dress
    9: "chaussures", 10: "chaussures",  # Left-shoe, Right-shoe
    16: "sac",  # Bag
    1: "accessoire", 3: "accessoire", 8: "accessoire", 17: "accessoire",  # Hat, Sunglasses, Belt, Scarf
}
BODY_LABELS = {2, 11, 12, 13, 14, 15}  # Hair, Face, Left/Right-leg, Left/Right-arm

PERSON_MIN_SHARE = 0.005  # share of the image covered by body parts to say someone is in it
GARMENT_MIN_SHARE = 0.04  # share of the person's pixels a garment must cover to count
COMPONENT_MIN_SHARE = 0.15  # drop specks smaller than this share of the garment's largest blob
# A hat, a belt or a scarf is one piece; accessory pixels scattered over the outfit are
# the segmenter mislabeling patterned clothing, not an accessory.
ACCESSORY_MIN_COHESION = 0.8
# Garment fragments are grouped per person — the connected silhouettes of everything
# that isn't background — so a dress split in two by the bag in front of it stays one
# item, while two people's tops are two items. Silhouettes are found on a downscaled
# mask, slightly dilated to bridge thin gaps (a hand off the hip).
GROUPING_GRID = 256
SILHOUETTE_GAP = 0.01  # share of the longest side bridged between silhouette fragments
SILHOUETTE_MIN_SHARE = 0.05  # smaller silhouettes (stray specks) attach to no one
CROP_PADDING = 0.08


@dataclass
class Garment:
    category: str  # DressMe category from the segmentation label
    share: float  # share of the person's pixels this garment covers
    image: "Image.Image"  # noqa: F821 — cut-out on a white square background

    def to_jpeg(self) -> bytes:
        buffer = io.BytesIO()
        self.image.save(buffer, format="JPEG", quality=92)
        return buffer.getvalue()


@dataclass
class Segmentation:
    person_detected: bool
    garments: list[Garment]


@lru_cache
def _load_segformer():
    from transformers import AutoModelForSemanticSegmentation

    return AutoModelForSemanticSegmentation.from_pretrained(SEGFORMER_REPO).eval()


def _label_map(image) -> np.ndarray:
    """Per-pixel ATR label at the image's own resolution. Preprocessing is done by
    hand (resize + ImageNet normalization, as in the repo's preprocessor_config.json)
    so the backend doesn't need torchvision just for that."""
    import torch
    from PIL import Image

    model = _load_segformer()
    pixels = np.asarray(image.resize((INPUT_SIZE, INPUT_SIZE), Image.BILINEAR), dtype=np.float32) / 255
    pixels = (pixels - IMAGENET_MEAN) / IMAGENET_STD
    tensor = torch.from_numpy(pixels.transpose(2, 0, 1)[None].copy())
    with torch.no_grad():
        logits = model(pixel_values=tensor).logits
        logits = torch.nn.functional.interpolate(logits, size=image.size[::-1], mode="bilinear")
    return logits.argmax(dim=1)[0].numpy()


def _silhouettes(labels: np.ndarray) -> list[np.ndarray]:
    """One full-resolution mask per person in the photo, largest first."""
    from scipy import ndimage

    height, width = labels.shape
    step = max(1, max(height, width) // GROUPING_GRID)
    small = labels[::step, ::step] != 0
    radius = max(1, round(SILHOUETTE_GAP * max(small.shape)))
    yy, xx = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    grouped, count = ndimage.label(ndimage.binary_dilation(small, structure=xx**2 + yy**2 <= radius**2))
    sizes = ndimage.sum(small, grouped, index=range(1, count + 1))
    keep = [i + 1 for i in np.argsort(-sizes) if sizes[i] >= SILHOUETTE_MIN_SHARE * sizes.max()]
    full = np.repeat(np.repeat(grouped, step, axis=0), step, axis=1)[:height, :width]
    return [(full == i) & (labels != 0) for i in keep]


def _cohesion(mask: np.ndarray) -> float:
    """Share of the mask held by its largest connected blob."""
    from scipy import ndimage

    components, count = ndimage.label(mask)
    if count <= 1:
        return 1.0
    return float(ndimage.sum(mask, components, index=range(1, count + 1)).max() / mask.sum())


def _clean_mask(mask: np.ndarray) -> np.ndarray:
    """Keeps the garment's main blobs (both shoes, a bag strap...) and drops stray
    mislabeled specks that would otherwise blow up the bounding box."""
    from scipy import ndimage

    components, count = ndimage.label(mask)
    if count <= 1:
        return mask
    sizes = ndimage.sum(mask, components, index=range(1, count + 1))
    keep = np.flatnonzero(sizes >= COMPONENT_MIN_SHARE * sizes.max()) + 1
    return np.isin(components, keep)


def _cut_out(image, mask: np.ndarray):
    from PIL import Image

    rows, cols = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))
    top, bottom, left, right = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
    pad = int(CROP_PADDING * max(bottom - top, right - left))
    side = max(bottom - top, right - left) + 2 * pad

    pixels = np.asarray(image).copy()
    pixels[~mask] = 255
    garment = Image.fromarray(pixels[top:bottom, left:right])
    canvas = Image.new("RGB", (side, side), "white")
    canvas.paste(garment, ((side - (right - left)) // 2, (side - (bottom - top)) // 2))
    return canvas


def segment_garments(image_bytes: bytes) -> Segmentation:
    from PIL import Image, ImageOps

    image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    labels = _label_map(image)

    person_pixels = int((labels != 0).sum())
    body_share = float(np.isin(labels, list(BODY_LABELS)).mean())
    if body_share < PERSON_MIN_SHARE or person_pixels == 0:
        return Segmentation(person_detected=False, garments=[])

    garments = []
    for category in dict.fromkeys(GARMENT_LABELS.values()):
        if category == "accessoire":
            continue  # handled per label below: a hat and a belt are two separate items
        ids = [i for i, c in GARMENT_LABELS.items() if c == category]
        garments.append((category, np.isin(labels, ids)))
    garments += [("accessoire", labels == i) for i, c in GARMENT_LABELS.items() if c == "accessoire"]

    found = []
    for silhouette in _silhouettes(labels):  # largest person first
        silhouette_pixels = int(silhouette.sum())
        worn = []
        for category, class_mask in garments:
            mask = class_mask & silhouette
            share = float(mask.sum()) / silhouette_pixels
            if share < GARMENT_MIN_SHARE:
                continue
            if category == "accessoire" and _cohesion(mask) < ACCESSORY_MIN_COHESION:
                continue
            mask = _clean_mask(mask)
            worn.append(Garment(category=category, share=round(share, 3), image=_cut_out(image, mask)))
        found += sorted(worn, key=lambda g: g.share, reverse=True)
    return Segmentation(person_detected=True, garments=found)
