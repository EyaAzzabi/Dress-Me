"""Test de la réponse du backend"""
import requests
import json

# Tester l'endpoint de recommandation
url = "http://localhost:8000/api/v1/recommendations/"

payload = {
    "occasion": "Entretien D'Embauche",
    "season": "spring",
    "temperature": 20.0,
    "num_outfits": 3
}

print("🌐 Appel API: POST /api/v1/recommendations/")
print(f"   Payload: {json.dumps(payload, indent=2)}")
print("\n⏳ Génération en cours...\n")

try:
    response = requests.post(url, json=payload, timeout=60)
    
    if response.status_code == 200:
        data = response.json()
        outfits = data.get("outfits", [])
        
        print(f"✅ SUCCÈS - {len(outfits)} outfits reçus")
        print("="*60)
        
        for i, outfit in enumerate(outfits, 1):
            item_ids = outfit.get("item_ids", [])
            print(f"\n📦 OUTFIT {i}:")
            print(f"   item_ids: {len(item_ids)} pièces")
            print(f"   IDs: {item_ids[:3]}..." if len(item_ids) > 3 else f"   IDs: {item_ids}")
            print(f"   Occasion: {outfit.get('occasion', 'N/A')}")
            print(f"   Score: {outfit.get('relevance_score', 0):.2f}")
            
            # Le problème: est-ce que item_ids contient vraiment 3+ IDs ?
            if len(item_ids) < 3:
                print(f"   ❌ PROBLÈME: Seulement {len(item_ids)} pièce(s) !")
            else:
                print(f"   ✅ OK: {len(item_ids)} pièces")
        
        print("\n" + "="*60)
        
        # Vérifier si toutes les item_ids sont différentes
        all_ids = [id for outfit in outfits for id in outfit.get("item_ids", [])]
        unique_ids = set(all_ids)
        
        print(f"\n📊 STATISTIQUES:")
        print(f"   Total IDs: {len(all_ids)}")
        print(f"   IDs uniques: {len(unique_ids)}")
        
        if len(all_ids) == len(unique_ids):
            print(f"   ✅ Aucune répétition")
        else:
            print(f"   ⚠️  {len(all_ids) - len(unique_ids)} répétition(s)")
    
    else:
        print(f"❌ ERREUR HTTP {response.status_code}")
        print(response.text[:500])

except requests.exceptions.Timeout:
    print("❌ TIMEOUT - Le backend prend trop de temps")
except Exception as e:
    print(f"❌ ERREUR: {e}")
