"""Script pour réindexer tous les vêtements existants et générer leurs embeddings"""
import sys
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.clothing_item import ClothingItem
from app.ml import vision_model
from app.db import vector_store
import os

print("🔄 Récupération de tous les vêtements...")
db: Session = SessionLocal()
items = db.query(ClothingItem).all()
print(f"✅ Trouvé {len(items)} vêtements à réindexer")

if len(items) == 0:
    print("Aucun vêtement à réindexer!")
    sys.exit(0)

success_count = 0
error_count = 0

for i, item in enumerate(items, 1):
    print(f"\n[{i}/{len(items)}] Traitement: {item.id}")
    print(f"   Catégorie: {item.category}")
    print(f"   Image: {item.image_url}")
    
    try:
        # Construire le chemin local de l'image
        # image_url peut être soit "/media/xxx.jpg" soit "http://localhost:8000/media/xxx.jpg"
        if "/media/" in item.image_url:
            filename = item.image_url.split("/media/")[-1]
            image_path = os.path.join("uploads", filename)
            
            if not os.path.exists(image_path):
                print(f"   ⚠️  Fichier introuvable: {image_path}")
                error_count += 1
                continue
            
            # Lire l'image comme bytes
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
            
            # Générer l'embedding
            result = vision_model.analyze_image(image_bytes)
            
            if "embedding" in result:
                # Stocker dans Pinecone
                vector_store.upsert_item_embedding(
                    item.id,
                    result["embedding"],
                    owner_id=item.owner_id,
                    category=item.category or "unknown"
                )
                print(f"   ✅ Embedding généré et stocké!")
                success_count += 1
            else:
                print(f"   ⚠️  Pas d'embedding généré")
                error_count += 1
        else:
            print(f"   ⚠️  Format d'URL non supporté")
            error_count += 1
            
    except Exception as e:
        print(f"   ❌ Erreur: {str(e)}")
        error_count += 1

db.close()

print("\n" + "="*50)
print(f"✅ Réindexation terminée!")
print(f"   Succès: {success_count}")
print(f"   Erreurs: {error_count}")
print("="*50)
