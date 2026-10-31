import io
import uuid
import numpy as np
import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.wardrobe_ingestion_agent import WardrobeIngestionAgent
from app.db.base import Base
from app.models.clothing_item import ClothingItem
from app.models.user import User
from app.services.cv_service import inspect_and_preprocess_image
from app.services.ml_color_service import extract_kmeans_palette
from app.services.wardrobe_rag_service import WardrobeRAGService


def _create_test_image_bytes(color=(180, 50, 50), size=(200, 200)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(email="wardrobe_user@dressme.tn", hashed_password="pw")
    session.add(user)
    session.commit()
    yield session, user
    session.close()


def test_cv_service_diagnostics():
    raw = _create_test_image_bytes(color=(120, 80, 200), size=(300, 300))
    diagnostics = inspect_and_preprocess_image(raw)

    assert "dimensions" in diagnostics
    assert diagnostics["dimensions"]["width"] == 300
    assert diagnostics["dimensions"]["height"] == 300
    assert "quality" in diagnostics
    quality = diagnostics["quality"]
    assert "sharpness" in quality
    assert "quality_score" in quality
    assert 0 <= quality["quality_score"] <= 100
    assert isinstance(quality["warnings"], list)


def test_ml_kmeans_color_palette():
    # Multi-colored image with 3 distinct stripes: Red, Green, Blue
    img = Image.new("RGB", (150, 150))
    for y in range(50):
        for x in range(150):
            img.putpixel((x, y), (200, 30, 30))  # red
    for y in range(50, 100):
        for x in range(150):
            img.putpixel((x, y), (30, 180, 50))  # green
    for y in range(100, 150):
        for x in range(150):
            img.putpixel((x, y), (30, 80, 200))  # blue

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()

    palette = extract_kmeans_palette(raw, n_colors=3)
    assert len(palette) == 3
    for entry in palette:
        assert "hex" in entry and entry["hex"].startswith("#")
        assert "rgb" in entry and len(entry["rgb"]) == 3
        assert "percentage" in entry and entry["percentage"] > 20
        assert "label" in entry

    # Monochromatic image returns 1 dominant cluster
    mono_raw = _create_test_image_bytes(color=(40, 100, 200), size=(80, 80))
    mono_palette = extract_kmeans_palette(mono_raw, n_colors=3)
    assert len(mono_palette) >= 1
    assert mono_palette[0]["label"] == "bleu"


def test_wardrobe_rag_duplicate_detection():
    rag = WardrobeRAGService()
    user_id = uuid.uuid4()
    item_id = uuid.uuid4()

    existing_item = ClothingItem(
        id=item_id,
        owner_id=user_id,
        image_url="https://dressme.tn/img/robe1.jpg",
        category="robe",
        colors=["rouge"],
        style="Casual",
    )

    vec = np.ones(512, dtype=np.float32)
    vec = vec / np.linalg.norm(vec)

    # Identical vector -> high similarity (>= 83%)
    context = rag.analyze_wardrobe_context(
        new_embedding=vec,
        new_attributes={"category": "robe", "style": "Casual"},
        existing_items=[existing_item],
        existing_embeddings={item_id: vec},
    )

    assert context["duplicate_warning"] is not None
    assert "similaire" in context["duplicate_warning"].lower()
    assert len(context["similar_items"]) >= 1
    assert context["similar_items"][0]["item_id"] == str(item_id)


def test_wardrobe_rag_complementary_pairings():
    rag = WardrobeRAGService()
    user_id = uuid.uuid4()
    bottom_id = uuid.uuid4()
    shoe_id = uuid.uuid4()

    bottom = ClothingItem(
        id=bottom_id,
        owner_id=user_id,
        image_url="https://dressme.tn/img/pantalon.jpg",
        category="bas",
        colors=["bleu marine"],
        style="Casual",
    )
    shoes = ClothingItem(
        id=shoe_id,
        owner_id=user_id,
        image_url="https://dressme.tn/img/sneakers.jpg",
        category="chaussures",
        colors=["blanc"],
        style="Casual",
    )

    vec = np.ones(512, dtype=np.float32)
    vec = vec / np.linalg.norm(vec)

    context = rag.analyze_wardrobe_context(
        new_embedding=vec,
        new_attributes={"category": "haut", "style": "Casual"},
        existing_items=[bottom, shoes],
        existing_embeddings={bottom_id: vec, shoe_id: vec},
    )

    pairings = context["recommended_pairings"]
    categories = [p["category"] for p in pairings]
    assert "bas" in categories or "chaussures" in categories


def test_wardrobe_ingestion_agent_run_mocked_vision(db_session, monkeypatch):
    session, user = db_session
    fake_attributes = {
        "category": "haut",
        "colors": ["noir"],
        "style": "Casual",
        "pattern": "uni",
        "season": "toutes_saisons",
        "confidence": {"category": 0.95, "colors": 0.9, "pattern": 0.8, "style": 0.8, "season": 0.8},
        "embedding": np.ones(512, dtype=np.float32),
        "category_uncertain": False,
    }

    class MockVisionAgent:
        def run(self, image_url: str):
            return fake_attributes

    agent = WardrobeIngestionAgent(db=session, vision_agent=MockVisionAgent())
    result = agent.run(image_url="https://fake.url/item.jpg", user_id=user.id)

    assert result["category"] == "haut"
    assert "cv_diagnostics" in result
    assert "kmeans_palette" in result
    assert "rag_analysis" in result
    assert "styling_insights" in result
    assert "editorial_advice" in result["styling_insights"]
    assert "care_tip" in result["styling_insights"]
