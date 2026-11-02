"""Vérifier combien d'utilisateurs existent et leurs items"""
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))

with engine.connect() as conn:
    # Compter les utilisateurs
    users = conn.execute(text("SELECT id, email FROM users")).fetchall()
    
    print(f"👥 UTILISATEURS dans la base: {len(users)}")
    print("="*60)
    
    for user in users:
        user_id = user[0]
        email = user[1]
        
        # Compter les items de cet utilisateur
        count = conn.execute(text("""
            SELECT COUNT(*) FROM clothing_items WHERE owner_id = :uid
        """), {"uid": user_id}).scalar()
        
        print(f"\n📧 {email}")
        print(f"   ID: {user_id}")
        print(f"   Items: {count} pièces")
        
        if count > 0:
            # Montrer quelques catégories
            cats = conn.execute(text("""
                SELECT category, COUNT(*) as c
                FROM clothing_items
                WHERE owner_id = :uid
                GROUP BY category
                ORDER BY c DESC
                LIMIT 3
            """), {"uid": user_id}).fetchall()
            
            print(f"   Catégories principales:")
            for cat in cats:
                print(f"      - {cat[0]}: {cat[1]}")
    
    print("\n" + "="*60)
    print("\n💡 L'utilisateur avec 21 pièces est celui que vous utilisez dans le frontend.")
    print("   Vérifiez que le token JWT du frontend correspond à cet utilisateur.")
