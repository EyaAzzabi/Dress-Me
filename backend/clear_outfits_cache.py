"""Supprimer tous les outfits en cache pour forcer la régénération"""
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))

with engine.connect() as conn:
    # Supprimer tous les outfits de votre compte
    result = conn.execute(text("""
        DELETE FROM outfits
        WHERE owner_id = 'f438dfec-2686-4459-9bb6-204b5b756de0'
    """))
    conn.commit()
    
    print(f"🗑️  {result.rowcount} outfit(s) supprimé(s)")
    print("✅ Cache vidé ! Le backend va maintenant générer de nouveaux outfits.")
    print("\n🔄 Rafraîchissez la page frontend et générez de nouveaux looks.")
