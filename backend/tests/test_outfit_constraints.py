"""Tests for outfit constraints by occasion."""

import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.clothing_item import ClothingItem
from app.models.user import User
from app.services.outfit_constraints import (
    OCCASION_CONSTRAINTS,
    filter_candidates_by_constraints,
    validate_outfit,
)


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


def _item(db, category: str, **kwargs) -> ClothingItem:
    """Helper to create a test clothing item."""
    item = ClothingItem(
        id=uuid.uuid4(),
        owner_id=db.user.id,
        image_url="http://example.com/test.jpg",
        category=category,
        **kwargs,
    )
    db.add(item)
    db.commit()
    return item


class TestValidateOutfit:
    """Test outfit validation against occasion constraints."""
    
    def test_travail_accepts_haut_bas(self, db):
        """Travail occasion should accept haut + bas combination."""
        haut = _item(db, "haut")
        bas = _item(db, "bas")
        shoes = _item(db, "chaussures")
        outfit = [haut, bas, shoes]
        
        is_valid, reason = validate_outfit(outfit, "travail", formality=4)
        
        assert is_valid, f"Should accept haut+bas for travail. Reason: {reason}"
    
    def test_travail_rejects_evening_dress(self, db):
        """Travail occasion should reject evening dresses."""
        robe = _item(db, "robe_soiree")
        outfit = [robe]
        
        is_valid, reason = validate_outfit(outfit, "travail", formality=4)
        
        assert not is_valid, "Should reject robe_soiree for travail"
        assert "robe_soiree" in reason.lower()
    
    def test_travail_rejects_formality_too_high(self, db):
        """Travail should reject extremely formal outfits (formality > 5)."""
        haut = _item(db, "haut")
        bas = _item(db, "bas")
        outfit = [haut, bas]
        
        is_valid, reason = validate_outfit(outfit, "travail", formality=5)
        
        # Travail allows formality 3-5, so 5 should be OK
        assert is_valid, f"Should accept formality=5 for travail. Reason: {reason}"
    
    def test_soiree_accepts_robe(self, db):
        """Soiree occasion should accept robe."""
        robe = _item(db, "robe")
        shoes = _item(db, "chaussures")
        outfit = [robe, shoes]
        
        is_valid, reason = validate_outfit(outfit, "soiree", formality=4)
        
        assert is_valid, f"Should accept robe for soiree. Reason: {reason}"
    
    def test_soiree_rejects_casual_wear(self, db):
        """Soiree should reject casual t-shirt and leggings."""
        tee = _item(db, "tee_shirt")
        leggings = _item(db, "leggings_sport")
        outfit = [tee, leggings]
        
        is_valid, reason = validate_outfit(outfit, "soiree", formality=4)
        
        assert not is_valid, "Should reject casual wear for soiree"
    
    def test_sport_accepts_athletic_wear(self, db):
        """Sport occasion should accept athletic wear (haut + bas)."""
        tee = _item(db, "haut")  # Sport accepts "haut" category
        leggings = _item(db, "bas")  # Sport accepts "bas" category
        shoes = _item(db, "chaussures")
        outfit = [tee, leggings, shoes]
        
        is_valid, reason = validate_outfit(outfit, "sport", formality=1)
        
        assert is_valid, f"Should accept athletic wear for sport. Reason: {reason}"
    
    def test_sport_rejects_formal_wear(self, db):
        """Sport should reject formal dresses and heels."""
        robe = _item(db, "robe_ceremonie")
        outfit = [robe]
        
        is_valid, reason = validate_outfit(outfit, "sport", formality=1)
        
        assert not is_valid, "Should reject formal dress for sport"
    
    def test_ceremonie_formality_must_be_5(self, db):
        """Ceremonie requires formality level 5."""
        robe = _item(db, "robe")
        outfit = [robe]
        
        is_valid_low, _ = validate_outfit(outfit, "ceremonie", formality=3)
        is_valid_high, _ = validate_outfit(outfit, "ceremonie", formality=5)
        
        assert not is_valid_low, "Should reject formality < 5 for ceremonie"
        assert is_valid_high, "Should accept formality = 5 for ceremonie"
    
    def test_no_occasion_accepts_anything(self, db):
        """No occasion constraints means everything is accepted."""
        robe = _item(db, "robe_soiree")
        outfit = [robe]
        
        is_valid, reason = validate_outfit(outfit, None, formality=1)
        
        assert is_valid, "Should accept any outfit when no occasion specified"
    
    def test_mix_robe_with_haut_bas_rejected(self, db):
        """Mixing robe with haut/bas should be rejected."""
        robe = _item(db, "robe")
        haut = _item(db, "haut")
        bas = _item(db, "bas")
        outfit = [robe, haut, bas]
        
        is_valid, reason = validate_outfit(outfit, "soiree", formality=4)
        
        assert not is_valid, "Should reject mixing robe with haut/bas"
        assert "mix" in reason.lower()


class TestFilterCandidates:
    """Test filtering candidates by occasion constraints."""
    
    def test_filter_removes_invalid_outfits(self, db):
        """Filter should remove outfits that violate constraints."""
        # Valid: haut + bas for travail
        valid_haut = _item(db, "haut")
        valid_bas = _item(db, "bas")
        valid_outfit = [valid_haut, valid_bas]
        
        # Invalid: robe_soiree for travail
        invalid_robe = _item(db, "robe_soiree")
        invalid_outfit = [invalid_robe]
        
        candidates = [
            (valid_outfit, 0.9, False),   # High score but valid
            (invalid_outfit, 0.95, False),  # Higher score but invalid
        ]
        
        filtered = filter_candidates_by_constraints(candidates, "travail", formality=4)
        
        assert len(filtered) == 1, "Should keep only valid outfit"
        assert filtered[0][0] == valid_outfit
    
    def test_filter_preserves_order_by_score(self, db):
        """Filter should preserve score ordering among valid outfits."""
        outfit1 = [_item(db, "haut"), _item(db, "bas")]
        outfit2 = [_item(db, "haut"), _item(db, "bas")]
        
        candidates = [
            (outfit1, 0.9, False),
            (outfit2, 0.8, False),
        ]
        
        filtered = filter_candidates_by_constraints(candidates, "travail", formality=4)
        
        assert len(filtered) == 2
        assert filtered[0][1] == 0.9  # Higher score first
        assert filtered[1][1] == 0.8
    
    def test_filter_with_no_occasion_returns_all(self, db):
        """With no occasion, all candidates should be returned."""
        outfit1 = [_item(db, "robe_soiree")]
        outfit2 = [_item(db, "tee_shirt_sport")]
        
        candidates = [
            (outfit1, 0.9, False),
            (outfit2, 0.8, False),
        ]
        
        filtered = filter_candidates_by_constraints(candidates, None, formality=4)
        
        assert len(filtered) == 2, "Should return all candidates when no occasion"


class TestConstraintRules:
    """Test that all constraint rules are well-defined."""
    
    def test_all_occasions_have_constraints(self):
        """Each occasion category should have constraint rules defined."""
        required_occasions = [
            "travail",
            "soiree",
            "ceremonie",
            "mariage",
            "casual_quotidien",
            "sport",
            "plage",
            "voyage",
        ]
        
        for occasion in required_occasions:
            assert occasion in OCCASION_CONSTRAINTS, f"Missing constraints for {occasion}"
    
    def test_constraints_have_valid_formality_ranges(self):
        """Each constraint should have valid min/max formality."""
        for occasion, constraint in OCCASION_CONSTRAINTS.items():
            assert 1 <= constraint.min_formality <= 5, f"Invalid min_formality for {occasion}"
            assert 1 <= constraint.max_formality <= 5, f"Invalid max_formality for {occasion}"
            assert constraint.min_formality <= constraint.max_formality, \
                f"min_formality > max_formality for {occasion}"
    
    def test_constraints_have_allowed_bases(self):
        """Each constraint should specify allowed base types."""
        for occasion, constraint in OCCASION_CONSTRAINTS.items():
            assert constraint.allowed_bases, f"No allowed_bases for {occasion}"
            for base in constraint.allowed_bases:
                assert base in ["haut_bas", "robe"], \
                    f"Invalid base type '{base}' for {occasion}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
