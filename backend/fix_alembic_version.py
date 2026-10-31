#!/usr/bin/env python3
"""
Script to fix Alembic version mismatch in Supabase database.
The database references a migration 'f8e9g0h1i2j3' that doesn't exist locally.
This script will update the alembic_version table directly.
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
print(f"Database URL: {DATABASE_URL[:DATABASE_URL.find('@')]}...{DATABASE_URL[DATABASE_URL.rfind(':'):]}")

try:
    # Create engine
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # Check current alembic version
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        current_version = result.scalar()
        print(f"Current alembic version in database: {current_version}")
        
        # Check what should be the head version
        # Based on alembic history, the head should be 'ab73d9e1c540'
        HEAD_VERSION = 'ab73d9e1c540'
        
        # Update to head version
        print(f"Updating to head version: {HEAD_VERSION}")
        conn.execute(text(f"UPDATE alembic_version SET version_num = '{HEAD_VERSION}'"))
        conn.commit()
        
        # Verify update
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        new_version = result.scalar()
        print(f"Updated alembic version in database: {new_version}")
        
        if new_version == HEAD_VERSION:
            print("✓ Successfully updated alembic version!")
        else:
            print(f"✗ Update failed. Current version: {new_version}")
            
except Exception as e:
    print(f"Error: {e}")
    exit(1)