#!/usr/bin/env python3
"""
Script to fix Alembic version mismatch in Supabase database.
Set database to correct HEAD version.
"""

import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in .env file")
    exit(1)

print(f"Connecting to database...")

try:
    # Create engine
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Clear all existing versions
        print("Clearing all existing alembic versions...")
        conn.execute(text("DELETE FROM alembic_version"))
        
        # Insert the correct HEAD version
        HEAD_VERSION = 'ab73d9e1c540'
        print(f"Inserting HEAD version: {HEAD_VERSION}")
        conn.execute(text(f"INSERT INTO alembic_version (version_num) VALUES ('{HEAD_VERSION}')"))
        conn.commit()
        
        # Verify
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        new_version = result.scalar()
        print(f"New alembic version in database: {new_version}")
        
        if new_version == HEAD_VERSION:
            print("✓ Successfully updated alembic version to HEAD!")
        else:
            print(f"✗ Update failed. Current version: {new_version}")
            
except Exception as e:
    print(f"Error: {e}")
    exit(1)