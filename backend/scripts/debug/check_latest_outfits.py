import os, requests
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from app.core.security import create_access_token

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    user_id = str(conn.execute(text(
        "SELECT id FROM users WHERE email = 'test@dressme.com'"
    )).scalar())

token = create_access_token(subject=user_id)
headers = {"Authorization": f"Bearer {token}"}

resp = requests.get("http://localhost:8000/api/v1/recommendations/outfits", headers=headers)
data = resp.json()
print(f"GET outfits => {len(data)} total")
for o in data:
    print(f"  occasion='{o.get('occasion')}' | score={o.get('relevance_score')} | items={len(o.get('item_ids',[]))}")
