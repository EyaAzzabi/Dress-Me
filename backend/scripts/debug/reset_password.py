import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from app.core.security import hash_password

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))

new_password = "Dressme123"
hashed = hash_password(new_password)

with engine.connect() as conn:
    conn.execute(
        text("UPDATE users SET hashed_password = :h WHERE email = 'test@dressme.com'"),
        {"h": hashed}
    )
    conn.commit()
    print("✓ Mot de passe mis à jour pour test@dressme.com")
    print(f"  Email    : test@dressme.com")
    print(f"  Password : {new_password}")
