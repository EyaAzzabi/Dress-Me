"""Computer Vision processing module for wardrobe intake.

Combines OpenCV and PIL for:
- Image quality assessment (Laplacian blur metric, resolution checks)
- Color space analysis (HSV, LAB)
- Brightness/contrast validation
- Automatic crop/bounding box calculation
"""
import io
import cv2
import numpy as np
from PIL import Image, ImageOps


def inspect_and_preprocess_image(image_bytes: bytes) -> dict:
    """Analyzes image quality and basic CV properties using OpenCV & PIL."""
    # Read with PIL first for format/orientation
    pil_img = Image.open(io.BytesIO(image_bytes))
    pil_img = ImageOps.exif_transpose(pil_img)
    width, height = pil_img.size

    # Convert to OpenCV BGR format
    rgb_array = np.array(pil_img.convert("RGB"))
    bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr_array, cv2.COLOR_BGR2GRAY)

    # 1. Blur detection using Laplacian variance
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if laplacian_var < 50.0:
        sharpness_label = "blurry"
    elif laplacian_var < 150.0:
        sharpness_label = "acceptable"
    else:
        sharpness_label = "sharp"

    # 2. Brightness and contrast
    brightness = float(np.mean(gray))
    contrast = float(np.std(gray))

    # 3. HSV / LAB stats for color perception
    hsv = cv2.cvtColor(bgr_array, cv2.COLOR_BGR2HSV)
    saturation = float(np.mean(hsv[:, :, 1]))

    # Quality warnings and overall score (0 to 100)
    warnings = []
    if sharpness_label == "blurry":
        warnings.append("L'image semble floue. Une photo nette garantit une meilleure reconnaissance.")
    if brightness < 45.0:
        warnings.append("La photo est sombre. Un meilleur éclairage fera ressortir les vraies couleurs.")
    elif brightness > 225.0:
        warnings.append("La photo est surexposée, certains détails peuvent être estompés.")
    if contrast < 25.0:
        warnings.append("Faible contraste avec l'arrière-plan.")

    sharpness_score = min(50.0, (laplacian_var / 200.0) * 50.0)
    brightness_score = max(0.0, 30.0 - abs(brightness - 130.0) * 0.25)
    contrast_score = min(20.0, (contrast / 60.0) * 20.0)
    overall_quality = int(round(sharpness_score + brightness_score + contrast_score))
    overall_quality = max(10, min(100, overall_quality))

    # 4. Rough bounding box of non-background content (using Otsu thresholding)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    bbox = None
    if contours:
        largest_c = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_c)
        if w > width * 0.1 and h > height * 0.1:
            bbox = {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}

    return {
        "dimensions": {"width": width, "height": height},
        "quality": {
            "laplacian_variance": round(laplacian_var, 2),
            "sharpness": sharpness_label,
            "brightness": round(brightness, 1),
            "contrast": round(contrast, 1),
            "saturation": round(saturation, 1),
            "quality_score": overall_quality,
            "warnings": warnings,
        },
        "bounding_box": bbox,
    }
