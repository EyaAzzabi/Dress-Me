import os, requests
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from app.core.security import create_access_token

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    r = conn.execute(text("SELECT id FROM users WHERE email = 'test@dressme.com'"))
    user_id = str(r.scalar())

token = create_access_token(subject=user_id)
headers = {"Authorization": f"Bearer {token}"}

# GET outfits saved in DB
resp = requests.get("http://localhost:8000/api/v1/recommendations/outfits", headers=headers)
data = resp.json()
print(f"GET /recommendations/outfits => {len(data)} outfits in DB")
for o in data:
    print(f"  id={o['id']}, occasion={o.get('occasion')}, score={o.get('relevance_score')}, items={o.get('item_ids')}")
