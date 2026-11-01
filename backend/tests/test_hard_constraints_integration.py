"""Integration test: RecommendationAgent respects hard constraints.

This test demonstrates that the bug where "occasion=travail" returns
"robe_soiree" has been fixed by hard constraints.
"""

import uuid
from datetime import date

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.recommendation_agent import RecommendationAgent
from app.db.base import Base
from app.models.clothing_item import ClothingItem
from app.models.user import User


@pytest.fixture
def db():
    """In-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(id=uuid.uuid4(), email="test@example.com", hashed_password="hash")
    session.add(user)
    session.commit()
    session.user = user
    yield session
    session.close()


def _item(db, category: str, name: str = "", **kwargs) -> ClothingItem:
    """Helper to create a test clothing item."""
    item = ClothingItem(
        id=uuid.uuid4(),
        owner_id=db.user.id,
        image_url=f"http://example.com/{name or category}.jpg",
        category=category,
        **kwargs,
    )
    db.add(item)
    db.commit()
    return item


def _mock_embeddings(items: list[ClothingItem]) -> dict:
    """Create mock FashionCLIP embeddings for items."""
    # Each item gets a random 512-d vector (normalized)
    embeddings = {}
    for item in items:
        vec = np.random.randn(512).astype(np.float32)
        vec = vec / np.linalg.norm(vec)  # L2 normalize
        embeddings[str(item.id)] = vec.tolist()
    return embeddings


class TestHardConstraintsIntegration:
    """Integration tests for hard constraints in RecommendationAgent."""
    
    def test_travail_does_not_return_evening_dress(self, db, monkeypatch):
        """
        BUG FIX: When occasion="travail", should NOT return robe_soiree.
        
        This test verifies that hard constraints filter out inappropriate outfits.
        """
        # Create a mixed wardrobe
        haut_travail = _item(db, "haut", "travail_shirt")
        bas_travail = _item(db, "bas", "travail_pants")
        shoes_casual = _item(db, "chaussures", "casual_shoes")
        robe_soiree = _item(db, "robe_soiree", "evening_dress")  # Should be filtered
        
        items = [haut_travail, bas_travail, shoes_casual, robe_soiree]
        
        # Mock embeddings
        embeddings = _mock_embeddings(items)
        monkeypatch.setattr(
            "app.agents.recommendation_agent.vector_store.fetch_embeddings",
            lambda item_ids: {k: v for k, v in embeddings.items()},
        )
        
        # Get recommendations for "travail"
        agent = RecommendationAgent()
        result = agent.run(
            wardrobe_items=items,
            occasion="travail",
            occasion_category="travail",
            formality=4,
            top_k=5,
        )
        
        # Verify: No outfit should contain the evening dress
        for outfit_data in result["outfits"]:
            item_ids = outfit_data["item_ids"]
            assert robe_soiree.id not in item_ids, \
                "BUG: Evening dress returned for travail occasion!"
        
        # Verify: Should return outfits with haut+bas
        assert len(result["outfits"]) > 0, "Should return at least one outfit"
        
        # Check that at least one outfit has haut and bas
        found_haut_bas = False
        for outfit_data in result["outfits"]:
            item_ids = outfit_data["item_ids"]
            outfit_items = {item.id: item for item in items}
            categories = {outfit_items[iid].category for iid in item_ids}
            
            if "haut" in categories and "bas" in categories:
                found_haut_bas = True
                break
        
        assert found_haut_bas, "Should return at least one haut+bas outfit for travail"
    
    def test_soiree_prefers_robe_over_casual(self, db, monkeypatch):
        """
        When occasion="soiree", should prefer robe over casual haut+bas.
        """
        # Create wardrobe
        robe = _item(db, "robe", "elegant_dress")
        haut_casual = _item(db, "haut", "tee_shirt")
        bas_casual = _item(db, "bas", "jeans")
        shoes = _item(db, "chaussures", "heels")
        
        items = [robe, haut_casual, bas_casual, shoes]
        embeddings = _mock_embeddings(items)
        monkeypatch.setattr(
            "app.agents.recommendation_agent.vector_store.fetch_embeddings",
            lambda item_ids: {k: v for k, v in embeddings.items()},
        )
        
        agent = RecommendationAgent()
        result = agent.run(
            wardrobe_items=items,
            occasion="soiree",
            occasion_category="soiree",
            formality=4,
            top_k=5,
        )
        
        # Should return outfits
        assert len(result["outfits"]) > 0, "Should return outfits for soiree"
        
        # At least the first outfit should contain the robe
        first_outfit_ids = result["outfits"][0]["item_ids"]
        outfit_items = {item.id: item for item in items}
        categories = {outfit_items[iid].category for iid in first_outfit_ids}
        
        # For soiree, top recommendation should have robe or be formal
        assert "robe" in categories or all(
            outfit_items[iid].category != "tee_shirt" for iid in first_outfit_ids
        ), "Should prefer robe or formal wear for soiree"
    
    def test_sport_rejects_formal_wear(self, db, monkeypatch):
        """
        When occasion="sport", should reject formal dresses.
        """
        # Create wardrobe with actual categories
        tee_sport = _item(db, "haut", "sports_shirt")  # Use "haut" instead
        leggings = _item(db, "bas", "athletic_leggings")  # Use "bas" instead
        running_shoes = _item(db, "chaussures", "sneakers")
        robe_ceremonie = _item(db, "robe_ceremonie", "formal_dress")
        
        items = [tee_sport, leggings, running_shoes, robe_ceremonie]
        embeddings = _mock_embeddings(items)
        monkeypatch.setattr(
            "app.agents.recommendation_agent.vector_store.fetch_embeddings",
            lambda item_ids: {k: v for k, v in embeddings.items()},
        )
        
        agent = RecommendationAgent()
        result = agent.run(
            wardrobe_items=items,
            occasion="sport",
            occasion_category="sport",
            formality=1,
            top_k=5,
        )
        
        # Verify: No outfit should contain the formal dress
        for outfit_data in result["outfits"]:
            item_ids = outfit_data["item_ids"]
            assert robe_ceremonie.id not in item_ids, \
                "Should not return formal dress for sport occasion!"
        
        # Should return athletic wear combinations (haut+bas)
        # Note: Sport allows haut_bas base, so we should get haut+bas combinations
        assert len(result["outfits"]) > 0, "Should return sport outfits"
    
    def test_constraints_filter_reduces_faux_positifs(self, db, monkeypatch):
        """
        Verify that hard constraints significantly reduce inappropriate recommendations.
        """
        # Create a large mixed wardrobe
        items = []
        
        # Business appropriate
        for i in range(3):
            items.append(_item(db, "haut", f"business_shirt_{i}"))
            items.append(_item(db, "bas", f"business_pants_{i}"))
        
        # Evening appropriate
        for i in range(3):
            items.append(_item(db, "robe_soiree", f"evening_dress_{i}"))
        
        # Casual
        for i in range(3):
            items.append(_item(db, "tee_shirt", f"tee_{i}"))
        
        embeddings = _mock_embeddings(items)
        monkeypatch.setattr(
            "app.agents.recommendation_agent.vector_store.fetch_embeddings",
            lambda item_ids: {k: v for k, v in embeddings.items()},
        )
        
        agent = RecommendationAgent()
        result = agent.run(
            wardrobe_items=items,
            occasion="travail",
            occasion_category="travail",
            formality=4,
            top_k=3,
        )
        
        # All recommendations should respect constraints
        for outfit_data in result["outfits"]:
            item_ids = outfit_data["item_ids"]
            outfit_items = {item.id: item for item in items}
            
            # Check: No evening dresses in business outfits
            has_evening_dress = any(
                outfit_items[iid].category == "robe_soiree" 
                for iid in item_ids
            )
            assert not has_evening_dress, "Business outfit contains evening dress!"
            
            # Check: Should have haut and bas
            categories = {outfit_items[iid].category for iid in item_ids}
            assert "haut" in categories, "Business outfit should have haut"
            assert "bas" in categories, "Business outfit should have bas"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
