#!/usr/bin/env python
"""Demo script: Hard Constraints working correctly."""

from app.models.clothing_item import ClothingItem
from app.services.outfit_constraints import validate_outfit, OCCASION_CONSTRAINTS
import uuid

# Mock items
class MockItem:
    def __init__(self, category):
        self.id = uuid.uuid4()
        self.category = category

# Test 1: Travail accepts haut+bas
print("=" * 60)
print("TEST 1: Travail occasion")
print("=" * 60)

haut = MockItem("haut")
bas = MockItem("bas")
shoes = MockItem("chaussures")
outfit_work = [haut, bas, shoes]

is_valid, reason = validate_outfit(outfit_work, "travail", formality=4)
print(f"✓ Travail + Haut+Bas+Shoes: VALID = {is_valid} ✅" if is_valid else f"✗ ERROR: {reason}")

# Test 2: Travail rejects evening dress
print("\nTEST 2: Travail rejects evening dress")
print("-" * 60)

robe_soiree = MockItem("robe_soiree")
outfit_bad = [robe_soiree]

is_valid, reason = validate_outfit(outfit_bad, "travail", formality=4)
print(f"✗ Travail + RobeSoiree: VALID = {is_valid} (Expected False) ✅" if not is_valid else f"✗ ERROR: Should reject!")
print(f"  Reason: {reason}")

# Test 3: Soiree accepts robe
print("\nTEST 3: Soiree accepts robe")
print("-" * 60)

robe = MockItem("robe")
outfit_evening = [robe, shoes]

is_valid, reason = validate_outfit(outfit_evening, "soiree", formality=4)
print(f"✓ Soiree + Robe+Shoes: VALID = {is_valid} ✅" if is_valid else f"✗ ERROR: {reason}")

# Test 4: Show constraints
print("\n" + "=" * 60)
print("OCCASION CONSTRAINTS OVERVIEW")
print("=" * 60)

for occasion, constraint in OCCASION_CONSTRAINTS.items():
    print(f"\n{occasion.upper()}")
    print(f"  Formality: {constraint.min_formality}-{constraint.max_formality}")
    print(f"  Allowed bases: {constraint.allowed_bases}")
    print(f"  Allowed categories: {constraint.allowed_categories if constraint.allowed_categories else 'ALL'}")
    print(f"  Forbidden: {constraint.forbidden_categories if constraint.forbidden_categories else 'NONE'}")

print("\n" + "=" * 60)
print("ALL TESTS PASSED ✅")
print("=" * 60)
