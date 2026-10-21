"""Background removal for clothing images.

Hybrid pipeline:
1. Uses `rembg` (u2net) if installed for high-quality e-commerce style cutout (works
   equally well on flat-lay clothes, hangers, or garments on people).
2. Falls back to SegFormer clothes parser (`mattmdjaga/segformer_b2_clothes` from
   `garment_segmentation.py`) which isolates garment pixels from background and human body.
3. If neither produces a valid mask (e.g., unrecognized image, flat texture), gracefully
   returns the original image bytes so wardrobe addition never fails.
"""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageOps

if TYPE_CHECKING:
    from app.services.storage import StorageService

logger = logging.getLogger(__name__)

CROP_PADDING = 0.08
MIN_GARMENT_PIXELS = 150


def _cut_out_with_alpha(image: Image.Image, alpha: Image.Image) -> Image.Image:
    """Centers and crops the cutout garment onto a clean white square canvas with padding,
    matching the format used across DressMe agents."""
    alpha_np = np.asarray(alpha) > 10
    rows = np.flatnonzero(alpha_np.any(axis=1))
    cols = np.flatnonzero(alpha_np.any(axis=0))
    if len(rows) == 0 or len(cols) == 0:
        return image.convert("RGB")

    top, bottom = rows[0], rows[-1] + 1
    left, right = cols[0], cols[-1] + 1
    width = right - left
    height = bottom - top

    pad = int(CROP_PADDING * max(width, height))
    side = max(width, height) + 2 * pad

    cropped_img = image.crop((left, top, right, bottom))
    cropped_alpha = alpha.crop((left, top, right, bottom))

    canvas = Image.new("RGB", (side, side), "white")
    canvas.paste(cropped_img, ((side - width) // 2, (side - height) // 2), mask=cropped_alpha)
    return canvas


def _remove_bg_with_rembg(image_bytes: bytes) -> bytes | None:
    try:
        import rembg  # type: ignore
    except ImportError:
        return None

    try:
        output_bytes = rembg.remove(image_bytes)
        img = Image.open(io.BytesIO(output_bytes))
        if img.mode != "RGBA":
            return output_bytes

        # Isolate alpha channel to build a clean centered canvas on white background
        r, g, b, alpha = img.split()
        rgb = Image.merge("RGB", (r, g, b))
        centered = _cut_out_with_alpha(rgb, alpha)

        buffer = io.BytesIO()
        centered.save(buffer, format="JPEG", quality=92)
        return buffer.getvalue()
    except Exception as exc:
        logger.warning("rembg execution failed, falling back to SegFormer: %s", exc)
        return None


def _remove_bg_with_segformer(image_bytes: bytes) -> bytes | None:
    try:
        from app.ml import garment_segmentation

        image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
        labels = garment_segmentation._label_map(image)

        # Look for garment labels first
        garment_ids = list(garment_segmentation.GARMENT_LABELS.keys())
        mask = np.isin(labels, garment_ids)

        # If no garment label was picked up, check if any non-background, non-body pixel exists
        if mask.sum() < MIN_GARMENT_PIXELS:
            body_ids = list(garment_segmentation.BODY_LABELS)
            candidate_mask = (labels != 0) & (~np.isin(labels, body_ids))
            if candidate_mask.sum() >= MIN_GARMENT_PIXELS:
                mask = candidate_mask

        if mask.sum() < MIN_GARMENT_PIXELS:
            return None

        cleaned_mask = garment_segmentation._clean_mask(mask)
        cutout = garment_segmentation._cut_out(image, cleaned_mask)

        buffer = io.BytesIO()
        cutout.save(buffer, format="JPEG", quality=92)
        return buffer.getvalue()
    except Exception as exc:
        logger.warning("SegFormer background removal failed: %s", exc)
        return None


def remove_image_background(image_bytes: bytes) -> tuple[bytes, str]:
    """Attempts background removal via rembg first, then SegFormer.

    Returns:
        tuple[bytes, content_type] with the resulting image (JPEG on clean white canvas)
        or original image if background removal could not be applied.
    """
    # 1. Try rembg
    rembg_result = _remove_bg_with_rembg(image_bytes)
    if rembg_result is not None:
        return rembg_result, "image/jpeg"

    # 2. Try SegFormer
    segformer_result = _remove_bg_with_segformer(image_bytes)
    if segformer_result is not None:
        return segformer_result, "image/jpeg"

    # 3. Graceful fallback to original image
    return image_bytes, "image/jpeg"


def process_and_upload_clean_image(image_url: str, storage_service: StorageService | None = None) -> str:
    """Fetches `image_url`, removes background, uploads the cleaned image to storage,
    and returns its new public URL.

    If anything fails (e.g. invalid URL in test, network error, storage unconfigured),
    it safely returns the original `image_url`.
    """
    if not image_url or not image_url.startswith(("http://", "https://")):
        return image_url

    try:
        import httpx

        response = httpx.get(image_url, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        content = response.content

        clean_bytes, content_type = remove_image_background(content)
        if clean_bytes == content:
            # Nothing was changed
            return image_url

        if storage_service is None:
            from app.services.storage import StorageService
            storage_service = StorageService()

        if not storage_service.is_configured():
            return image_url

        return storage_service.upload_image(clean_bytes, content_type)
    except Exception as exc:
        logger.warning("Background removal process failed for %s: %s", image_url, exc)
        return image_url
