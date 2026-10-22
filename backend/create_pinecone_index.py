"""Script pour créer l'index Pinecone automatiquement"""
from app.db.vector_store import ensure_index, get_vector_client

print("🔄 Vérification de la connexion Pinecone...")
client = get_vector_client()

if client is None:
    print("❌ Erreur: Impossible de se connecter à Pinecone")
    print("Vérifiez que PINECONE_API_KEY est défini dans .env")
    exit(1)

print("✅ Connecté à Pinecone!")
print(f"Indexes existants: {[idx.name for idx in client.list_indexes()]}")

print("\n🔄 Création de l'index dressme-clothing-embeddings...")
ensure_index()

print("\n✅ Index créé avec succès!")
print(f"Indexes après création: {[idx.name for idx in client.list_indexes()]}")
