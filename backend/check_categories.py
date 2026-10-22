"""Script pour vérifier les catégories des vêtements"""
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.clothing_item import ClothingItem
from collections import Counter

db: Session = SessionLocal()
items = db.query(ClothingItem).all()

print(f"Total: {len(items)} vêtements\n")

categories = Counter(item.category for item in items)
print("Répartition par catégorie:")
for cat, count in categories.most_common():
    print(f"  - {cat}: {count}")

print("\nDétail des vêtements:")
for item in items:
    print(f"  [{item.category}] {item.id}")

db.close()

# Calcul des combinaisons possibles
hauts = categories.get("haut", 0)
bas = categories.get("bas", 0)
robes = categories.get("robe", 0)

print(f"\nCombinaisons possibles:")
print(f"  - Haut + Bas: {hauts} × {bas} = {hauts * bas} combinaisons")
print(f"  - Robes seules: {robes} combinaisons")
print(f"  - Total bases: {hauts * bas + robes}")
