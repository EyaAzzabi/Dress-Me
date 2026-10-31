#!/usr/bin/env python3
"""
Apply missing tables to Supabase database.
We stamped alembic version without running the actual migrations.
This script creates the missing tables directly.
"""
import os
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

inspector = inspect(engine)
existing_tables = inspector.get_table_names()
print(f"Existing tables: {existing_tables}")

MISSING_TABLES_SQL = []

if "recommendation_feedback" not in existing_tables:
    print("⚠ Missing: recommendation_feedback — will create")
    MISSING_TABLES_SQL.append("""
    CREATE TABLE IF NOT EXISTS recommendation_feedback (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        outfit_id UUID NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
        rating VARCHAR(16) NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_recommendation_feedback_rating CHECK (rating IN ('like','dislike','worn')),
        CONSTRAINT uq_recommendation_feedback_outfit UNIQUE (outfit_id)
    );
    CREATE INDEX IF NOT EXISTS ix_recommendation_feedback_owner_id
        ON recommendation_feedback(owner_id);
    """)
else:
    print("✓ recommendation_feedback already exists")

if "wear_logs" not in existing_tables:
    print("⚠ Missing: wear_logs — will create")
    MISSING_TABLES_SQL.append("""
    CREATE TABLE IF NOT EXISTS wear_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        item_id UUID NOT NULL REFERENCES clothing_items(id) ON DELETE CASCADE,
        worn_on DATE NOT NULL DEFAULT CURRENT_DATE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
else:
    print("✓ wear_logs already exists")

if not MISSING_TABLES_SQL:
    print("\n✓ All tables exist, nothing to create.")
else:
    with engine.connect() as conn:
        for sql in MISSING_TABLES_SQL:
            conn.execute(text(sql))
        conn.commit()
    print("\n✓ Missing tables created successfully!")
    
    # Verify
    inspector2 = inspect(engine)
    new_tables = inspector2.get_table_names()
    print(f"Tables now: {new_tables}")
