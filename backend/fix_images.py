"""
Replace broken local image URLs with real placeholder images
so the wardrobe display works without uploading actual photos.
"""
import os
import requests
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

# Placeholder images per category (real public URLs, no auth needed)
PLACEHOLDERS = {
    "haut":        "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&q=80",
    "bas":         "https://images.unsplash.com/photo-1542272604-787c3835535d?w=400&q=80",
    "robe":        "https://images.unsplash.com/photo-1612336307429-8a898d10e223?w=400&q=80",
    "veste":       "https://images.unsplash.com/photo-1551537482-f2075a1d41f2?w=400&q=80",
    "chaussures":  "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&q=80",
    "sac":         "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=400&q=80",
    "accessoire":  "https://images.unsplash.com/photo-1618354691373-d851c5c3a990?w=400&q=80",
    "manteau":     "https://images.unsplash.com/photo-1539533018447-63fcce2678e3?w=400&q=80",
}
DEFAULT = "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?w=400&q=80"

with engine.connect() as conn:
    # Get all items with broken local URLs
    rows = conn.execute(text("""
        SELECT id, category, image_url 
        FROM clothing_items 
        WHERE image_url LIKE 'http://localhost%'
    """)).fetchall()

    print(f"Found {len(rows)} items with local URLs")

    fixed = 0
    for item_id, category, old_url in rows:
        new_url = PLACEHOLDERS.get(category or "", DEFAULT)
        conn.execute(text(
            "UPDATE clothing_items SET image_url = :url WHERE id = :id"
        ), {"url": new_url, "id": item_id})
        print(f"  ✓ {category or 'unknown':12s} → {new_url[:60]}...")
        fixed += 1

    conn.commit()
    print(f"\n✓ Fixed {fixed} items")
