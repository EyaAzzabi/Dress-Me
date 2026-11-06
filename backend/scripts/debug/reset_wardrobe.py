"""
Supprime tous les vêtements et tenues de test@dressme.com
pour repartir avec de vraies photos uploadées depuis la machine.
"""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Récupérer l'ID du user
    user_id = conn.execute(text(
        "SELECT id FROM users WHERE email = 'test@dressme.com'"
    )).scalar()
    print(f"User: test@dressme.com ({user_id})")

    # Supprimer les feedbacks liés aux tenues
    r = conn.execute(text(
        "DELETE FROM recommendation_feedback WHERE owner_id = :uid"
    ), {"uid": user_id})
    print(f"  ✓ Feedbacks supprimés: {r.rowcount}")

    # Supprimer les tenues
    r = conn.execute(text(
        "DELETE FROM outfits WHERE owner_id = :uid"
    ), {"uid": user_id})
    print(f"  ✓ Tenues supprimées: {r.rowcount}")

    # Supprimer les vêtements
    r = conn.execute(text(
        "DELETE FROM clothing_items WHERE owner_id = :uid"
    ), {"uid": user_id})
    print(f"  ✓ Vêtements supprimés: {r.rowcount}")

    conn.commit()
    print("\n✓ Dressing vidé. Tu peux maintenant uploader tes propres photos.")
