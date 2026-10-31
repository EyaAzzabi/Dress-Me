#!/usr/bin/env python3
"""
Test recommendation with an existing user that has wardrobe items.
"""
import os
import requests
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

BASE_URL = 'http://localhost:8000/api/v1'
DATABASE_URL = os.getenv("DATABASE_URL")

# Find a user with clothing items
engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT u.id, u.email, COUNT(c.id) as item_count
        FROM users u
        LEFT JOIN clothing_items c ON c.owner_id = u.id
        GROUP BY u.id, u.email
        HAVING COUNT(c.id) > 0
        ORDER BY item_count DESC
        LIMIT 5
    """))
    users_with_items = result.fetchall()

print("Users with wardrobe items:")
for user in users_with_items:
    print(f"  {user[1]} — {user[2]} items")

if not users_with_items:
    print("No users with wardrobe items found!")
    exit(1)

# Use the user with the most items
best_user_id = str(users_with_items[0][0])
best_user_email = users_with_items[0][1]
print(f"\nUsing: {best_user_email} ({users_with_items[0][2]} items)")

# Generate a token directly (bypass password)
from app.core.security import create_access_token
token = create_access_token(subject=best_user_id)
print(f"Generated token for testing: {token[:60]}...")

# Call the recommendation endpoint
headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}

payload = {
    "occasion": "casual",
    "weather": "ensoleillé",
    "season": "printemps",
    "city": "Tunis",
    "request_text": "Une tenue décontractée pour sortir"
}

print(f"\nCalling POST {BASE_URL}/recommendations/outfits...")
print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")

try:
    response = requests.post(
        f'{BASE_URL}/recommendations/outfits',
        json=payload,
        headers=headers,
        timeout=60
    )
    
    print(f"\nStatus: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        outfits = data.get('outfits', [])
        print(f"✓ Got {len(outfits)} outfit(s)\n")
        
        for i, outfit in enumerate(outfits[:3]):  # show max 3
            print(f"{'='*50}")
            print(f"Outfit {i+1}")
            print(f"  Items: {outfit.get('item_ids', [])}")
            print(f"  Score: {outfit.get('relevance_score')}")
            print(f"  Explanation: {str(outfit.get('explanation', ''))[:200]}")
            
            # New agentic fields
            critic = outfit.get('critic_score')
            if critic:
                print(f"\n  ⚖️  Critic Score:")
                for k, v in critic.items():
                    print(f"      {k}: {v}")
            
            react = outfit.get('react_trace', [])
            if react:
                print(f"\n  🧠 ReAct Trace ({len(react)} steps):")
                for step in react[:3]:
                    print(f"      [{step.get('step')}] {str(step.get('thought',''))[:100]}")
            
            guidelines = outfit.get('style_guidelines_used', [])
            if guidelines:
                print(f"\n  📚 Style Guidelines ({len(guidelines)}):")
                for g in guidelines[:2]:
                    print(f"      - {g[:100]}")
    else:
        print(f"✗ Error: {response.text[:500]}")
        
except Exception as e:
    print(f"✗ Exception: {e}")
