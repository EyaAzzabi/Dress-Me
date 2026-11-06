from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))

user_id = 'f438dfec-2686-4459-9bb6-204b5b756de0'

with engine.connect() as conn:
    # Marquer toutes les pièces comme 'toutes_saisons'
    result = conn.execute(text("""
        UPDATE clothing_items
        SET season = 'toutes_saisons'
        WHERE owner_id = :uid
        AND (season IS NULL OR season = 'hiver')
    """), {'uid': user_id})
    conn.commit()
    
    print(f"✅ {result.rowcount} pièces mises à jour")
    print("Redémarrez le backend et testez !")
