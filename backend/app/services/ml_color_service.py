"""Machine Learning color extraction module using K-Means clustering.

Extracts exact hex codes, RGB values, and distribution percentages from garment images.
"""
import io
import numpy as np
from PIL import Image
from sklearn.cluster import KMeans

# Reference color centroids for human-readable color naming
COLOR_NAMES_RGB = {
    "noir": (25, 25, 25),
    "blanc": (245, 245, 245),
    "gris": (128, 128, 128),
    "beige": (225, 210, 185),
    "marron": (110, 60, 30),
    "bleu marine": (20, 35, 75),
    "bleu": (40, 110, 200),
    "bleu ciel": (135, 190, 235),
    "vert": (40, 140, 60),
    "vert olive": (105, 120, 60),
    "kaki": (130, 125, 80),
    "rouge": (200, 35, 35),
    "bordeaux": (115, 20, 40),
    "rose": (230, 130, 160),
    "orange": (235, 120, 30),
    "jaune": (240, 200, 40),
    "violet": (120, 50, 140),
    "creme": (250, 245, 230),
}


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _nearest_color_name(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    best_name = "inconnu"
    min_dist = float("inf")
    for name, (cr, cg, cb) in COLOR_NAMES_RGB.items():
        # Euclidean distance in RGB
        dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if dist < min_dist:
            min_dist = dist
            best_name = name
    return best_name


def extract_kmeans_palette(image_bytes: bytes, n_colors: int = 4) -> list[dict]:
    """Runs K-Means clustering on the image pixels to extract dominant color palette.
    
    Ignores extreme white background pixels (common in catalog photos) if non-background
    pixels are plentiful.
    """
    raw_img = Image.open(io.BytesIO(image_bytes))
    if raw_img.mode in ("RGBA", "LA") or (raw_img.mode == "P" and "transparency" in raw_img.info):
        bg = Image.new("RGB", raw_img.size, (255, 255, 255))
        if raw_img.mode != "RGBA":
            raw_img = raw_img.convert("RGBA")
        bg.paste(raw_img, mask=raw_img.split()[3])
        image = bg
    else:
        image = raw_img.convert("RGB")
    # Downscale for fast clustering
    image.thumbnail((150, 150))
    pixels = np.array(image).reshape(-1, 3)

    # Filter out near-pure white background (R>245, G>245, B>245) if garment pixels exist
    non_bg_mask = ~((pixels[:, 0] > 245) & (pixels[:, 1] > 245) & (pixels[:, 2] > 245))
    valid_pixels = pixels[non_bg_mask] if np.sum(non_bg_mask) > len(pixels) * 0.1 else pixels

    if len(valid_pixels) < n_colors:
        valid_pixels = pixels

    kmeans = KMeans(n_clusters=n_colors, n_init=3, random_state=42)
    labels = kmeans.fit_predict(valid_pixels)
    counts = np.bincount(labels, minlength=len(kmeans.cluster_centers_))
    total_count = max(1, len(labels))

    palette = []
    # Sort clusters by proportion descending
    sorted_indices = np.argsort(-counts)
    for idx in sorted_indices:
        if counts[idx] == 0:
            continue
        centroid = kmeans.cluster_centers_[idx].astype(int)
        r, g, b = int(centroid[0]), int(centroid[1]), int(centroid[2])
        hex_code = _rgb_to_hex(r, g, b)
        share = float(counts[idx] / total_count)
        color_name = _nearest_color_name((r, g, b))
        palette.append({
            "hex": hex_code,
            "rgb": [r, g, b],
            "percentage": round(share * 100, 1),
            "label": color_name,
        })

    return palette
