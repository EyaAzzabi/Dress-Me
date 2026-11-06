"""Script pour vérifier l'état des tables"""
from app.db.session import engine
from sqlalchemy import text, inspect

inspector = inspect(engine)
tables = inspector.get_table_names()

print("Tables existantes dans la base de données:")
for table in sorted(tables):
    print(f"  - {table}")

print(f"\nTotal: {len(tables)} tables")

# Tables attendues
expected_tables = [
    'users', 'clothing_items', 'outfits', 'scheduled_outfits', 
    'wear_logs', 'packing_lists', 'wishlist_items', 'purchase_history'
]

missing = set(expected_tables) - set(tables)
if missing:
    print(f"\n❌ Tables manquantes: {', '.join(sorted(missing))}")
else:
    print("\n✅ Toutes les tables attendues sont présentes")
