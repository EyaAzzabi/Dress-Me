"""Test direct de l'API backend"""
import requests
import json

# Test avec votre vrai token JWT
url = "http://localhost:8000/api/v1/recommendations/"

headers = {
    "Content-Type": "application/json",
    # TODO: Remplacer par votre token JWT du frontend
    # Ouvrez la console Chrome (F12) et tapez: localStorage.getItem('token')
}

# Test 1: Quotidien
print("🧪 TEST 1: QUOTIDIEN")
print("="*60)
payload = {
    "occasion": "Quotidien",
    "season": "spring",
    "num_outfits": 1
}

try:
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        outfits = data.get("outfits", [])
        
        if outfits:
            outfit = outfits[0]
            print(f"✅ Outfit reçu:")
            print(f"   Occasion: {outfit.get('occasion')}")
            print(f"   Item IDs: {outfit.get('item_ids')}")
            print(f"   Score: {outfit.get('relevance_score')}")
        else:
            print("❌ Aucun outfit dans la réponse")
    else:
        print(f"❌ Erreur {response.status_code}")
        if response.status_code == 401:
            print("   🔑 Vous devez ajouter votre token JWT dans headers!")
            print("   1. Ouvrez Chrome DevTools (F12)")
            print("   2. Console > tapez: localStorage.getItem('token')")
            print("   3. Copiez le token et ajoutez-le dans ce script")
        else:
            print(f"   {response.text[:200]}")
            
except Exception as e:
    print(f"❌ Erreur: {e}")

print("\n" + "="*60)
print("💡 Si vous voyez un token requis, récupérez-le depuis le frontend")
print("   et relancez ce script avec le token dans headers['Authorization']")
