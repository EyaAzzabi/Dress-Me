import io
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.core.config import get_settings
from app.services.storage import StorageService


def _clean_cutout(img: Image.Image) -> Image.Image:
    """Removes solid background around a garment, producing a transparent cutout with cropped bounding box."""
    rgba = img.convert("RGBA")
    arr = np.array(rgba)

    # If image already has transparency, use it
    if np.any(arr[:, :, 3] < 220):
        bbox = rgba.getbbox()
        return rgba.crop(bbox) if bbox else rgba

    # Sample corners to determine background color
    corners = np.array([arr[0, 0, :3], arr[0, -1, :3], arr[-1, 0, :3], arr[-1, -1, :3]])
    bg_color = np.median(corners, axis=0)

    # Difference from background color
    diff = np.linalg.norm(arr[:, :, :3] - bg_color, axis=2)
    # Mask background pixels
    is_bg = diff < 38
    arr[is_bg, 3] = 0

    clean = Image.fromarray(arr)
    bbox = clean.getbbox()
    return clean.crop(bbox) if bbox else clean


def _apply_drop_shadow(
    img: Image.Image, blur: int = 14, offset: tuple[int, int] = (6, 10), opacity: int = 40
) -> Image.Image:
    """Adds a soft diffuse luxury studio drop shadow to a cutout."""
    w, h = img.size
    pad = blur * 2
    res = Image.new("RGBA", (w + pad, h + pad), (0, 0, 0, 0))
    alpha = img.split()[-1]

    shadow_patch = Image.new("RGBA", (w, h), (35, 30, 28, opacity))
    res.paste(shadow_patch, (pad // 2 + offset[0], pad // 2 + offset[1]), mask=alpha)
    res = res.filter(ImageFilter.GaussianBlur(blur / 2))
    res.paste(img, (pad // 2, pad // 2), mask=img)
    return res


def _load_image(item: Any) -> Image.Image | None:
    """Loads image from local storage or URL."""
    url = getattr(item, "image_url", None) or (item.get("image_url") if isinstance(item, dict) else None)
    if not url:
        return None

    settings = get_settings()
    upload_dir = settings.local_storage_dir or "./uploads"

    # Try local file first
    if "/media/" in url:
        filename = url.split("/media/")[-1].split("?")[0]
        local_p = Path(upload_dir) / filename
        if local_p.exists():
            try:
                return Image.open(local_p)
            except Exception:
                pass

    # Fallback to HTTP
    try:
        import httpx

        resp = httpx.get(url, timeout=10.0, follow_redirects=True)
        if resp.status_code == 200:
            return Image.open(io.BytesIO(resp.content))
    except Exception:
        pass
    return None


def create_outfit_moodboard(items: list[Any], title: str | None = None) -> str:
    """Generates an editorial Flat Lay / Moodboard of an outfit without any avatar mannequin."""
    storage = StorageService()
    if not items:
        # Empty placeholder moodboard
        blank = Image.new("RGB", (1000, 1200), (250, 248, 245))
        buf = io.BytesIO()
        blank.save(buf, format="JPEG", quality=90)
        return storage.upload_image(buf.getvalue(), "image/jpeg")

    canvas_w, canvas_h = 1000, 1250
    # Warm off-white studio background
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (251, 249, 246, 255))
    draw = ImageDraw.Draw(canvas)

    # Editorial frame lines
    draw.rectangle([24, 24, canvas_w - 24, canvas_h - 24], outline=(235, 230, 224, 255), width=1)
    draw.rectangle([28, 28, canvas_w - 28, canvas_h - 28], outline=(242, 238, 233, 255), width=1)

    # Categorize items
    by_cat: dict[str, list[tuple[Any, Image.Image]]] = {}
    for it in items:
        cat = (getattr(it, "category", None) or (it.get("category") if isinstance(it, dict) else "") or "").lower()
        img = _load_image(it)
        if img is not None:
            clean = _clean_cutout(img)
            by_cat.setdefault(cat, []).append((it, clean))

    placed_layers: list[tuple[Image.Image, int, int]] = []

    has_robe = "robe" in by_cat
    has_haut = "haut" in by_cat
    has_bas = "bas" in by_cat

    if has_robe:
        # Robe centered as primary focus
        _, r_img = by_cat["robe"][0]
        rw = 520
        rh = min(820, int(r_img.height * (rw / r_img.width)))
        r_resized = r_img.resize((rw, rh), Image.Resampling.LANCZOS)
        r_sh = _apply_drop_shadow(r_resized, blur=18, offset=(8, 14), opacity=45)
        placed_layers.append((r_sh, int((canvas_w - r_sh.width) / 2), 120))

        # Chaussures bottom right
        if "chaussures" in by_cat:
            _, s_img = by_cat["chaussures"][0]
            sw = 280
            sh = int(s_img.height * (sw / s_img.width))
            s_sh = _apply_drop_shadow(s_img.resize((sw, sh), Image.Resampling.LANCZOS), blur=14, offset=(6, 10))
            placed_layers.append((s_sh, canvas_w - s_sh.width - 60, canvas_h - s_sh.height - 80))

        # Sac / Accessoire top left or bottom left
        if "sac" in by_cat:
            _, b_img = by_cat["sac"][0]
            bw = 250
            bh = int(b_img.height * (bw / b_img.width))
            b_sh = _apply_drop_shadow(b_img.resize((bw, bh), Image.Resampling.LANCZOS))
            placed_layers.append((b_sh, 60, 200))

        if "veste" in by_cat:
            _, v_img = by_cat["veste"][0]
            vw = 360
            vh = int(v_img.height * (vw / v_img.width))
            v_sh = _apply_drop_shadow(v_img.resize((vw, vh), Image.Resampling.LANCZOS))
            placed_layers.append((v_sh, 50, 100))

    elif has_haut or has_bas:
        # Haut centered top, Bas centered below
        haut_bottom_y = 520
        if has_haut:
            _, h_img = by_cat["haut"][0]
            hw = 480
            hh = min(480, int(h_img.height * (hw / h_img.width)))
            h_resized = h_img.resize((hw, hh), Image.Resampling.LANCZOS)
            h_sh = _apply_drop_shadow(h_resized, blur=16, offset=(6, 12), opacity=45)
            hx = int((canvas_w - h_sh.width) / 2)
            placed_layers.append((h_sh, hx, 70))
            haut_bottom_y = 70 + hh

        if has_bas:
            _, b_img = by_cat["bas"][0]
            bw = 420
            bh = min(560, int(b_img.height * (bw / b_img.width)))
            b_resized = b_img.resize((bw, bh), Image.Resampling.LANCZOS)
            b_sh = _apply_drop_shadow(b_resized, blur=16, offset=(6, 12), opacity=45)
            bx = int((canvas_w - b_sh.width) / 2)
            # Overlap bas slightly behind/under haut
            by_pos = max(haut_bottom_y - 40, 480)
            placed_layers.append((b_sh, bx, by_pos))

        # Veste draped slightly to the side
        if "veste" in by_cat:
            _, v_img = by_cat["veste"][0]
            vw = 340
            vh = int(v_img.height * (vw / v_img.width))
            v_sh = _apply_drop_shadow(v_img.resize((vw, vh), Image.Resampling.LANCZOS))
            placed_layers.append((v_sh, 45, 100))

        # Chaussures at bottom corner
        if "chaussures" in by_cat:
            _, s_img = by_cat["chaussures"][0]
            sw = 270
            sh = int(s_img.height * (sw / s_img.width))
            s_sh = _apply_drop_shadow(s_img.resize((sw, sh), Image.Resampling.LANCZOS))
            placed_layers.append((s_sh, canvas_w - s_sh.width - 55, canvas_h - s_sh.height - 75))

        # Sac on bottom left
        if "sac" in by_cat:
            _, bg_img = by_cat["sac"][0]
            gw = 240
            gh = int(bg_img.height * (gw / bg_img.width))
            g_sh = _apply_drop_shadow(bg_img.resize((gw, gh), Image.Resampling.LANCZOS))
            placed_layers.append((g_sh, 55, canvas_h - g_sh.height - 85))

        # Accessoire styled subtly
        if "accessoire" in by_cat:
            _, a_img = by_cat["accessoire"][0]
            aw = 190
            ah = int(a_img.height * (aw / a_img.width))
            a_sh = _apply_drop_shadow(a_img.resize((aw, ah), Image.Resampling.LANCZOS))
            placed_layers.append((a_sh, canvas_w - a_sh.width - 60, 110))

    else:
        # Generic balanced collage for other item groups
        all_cutouts = [img for sub in by_cat.values() for _, img in sub]
        n = len(all_cutouts)
        if n == 1:
            img = all_cutouts[0]
            w = 550
            h = int(img.height * (w / img.width))
            sh = _apply_drop_shadow(img.resize((w, h), Image.Resampling.LANCZOS))
            placed_layers.append((sh, int((canvas_w - sh.width) / 2), int((canvas_h - sh.height) / 2)))
        else:
            cols = 2
            rows = max(1, (n + 1) // 2)
            cell_w = (canvas_w - 120) // cols
            cell_h = (canvas_h - 160) // rows
            for idx, img in enumerate(all_cutouts):
                r = idx // cols
                c = idx % cols
                scale = min(cell_w * 0.85 / img.width, cell_h * 0.85 / img.height)
                nw, nh = int(img.width * scale), int(img.height * scale)
                sh = _apply_drop_shadow(img.resize((nw, nh), Image.Resampling.LANCZOS))
                pos_x = 60 + c * cell_w + int((cell_w - sh.width) / 2)
                pos_y = 80 + r * cell_h + int((cell_h - sh.height) / 2)
                placed_layers.append((sh, pos_x, pos_y))

    # Paste all layers
    for layer, lx, ly in placed_layers:
        canvas.paste(layer, (lx, ly), mask=layer)

    # Discreet luxury stamp at the bottom
    text = "D R E S S M E   ·   S T U D I O   L O O K"
    draw.text((int(canvas_w / 2), canvas_h - 45), text, fill=(168, 160, 150, 220), anchor="ms")

    # Export JPEG
    out_buf = io.BytesIO()
    canvas.convert("RGB").save(out_buf, format="JPEG", quality=94)
    return storage.upload_image(out_buf.getvalue(), "image/jpeg")
