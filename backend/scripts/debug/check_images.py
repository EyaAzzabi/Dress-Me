import os, requests
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT id, image_url FROM clothing_items WHERE owner_id = "
        "(SELECT id FROM users WHERE email = 'test@dressme.com') LIMIT 5"
    )).fetchall()

print("Sample image URLs:")
for row in rows:
    url = row[1]
    print(f"\n  {url}")
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        print(f"  => HTTP {r.status_code}")
    except Exception as e:
        print(f"  => ERROR: {e}")
