#!/usr/bin/env python3
"""
Script to fix Alembic version mismatch in Supabase database.
There are two rows in alembic_version table.
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
        # Check all alembic versions
        result = conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
        versions = [row[0] for row in result]
        print(f"All alembic versions in database: {versions}")
        
        # Based on alembic history, the head should be 'ab73d9e1c540'
        HEAD_VERSION = 'ab73d9e1c540'
        
        if HEAD_VERSION in versions:
            print(f"✓ Head version {HEAD_VERSION} already exists in database")
            
            # Delete the problematic version if it exists
            BAD_VERSION = 'f8e9g0h1i2j3'
            if BAD_VERSION in versions:
                print(f"Deleting bad version: {BAD_VERSION}")
                conn.execute(text(f"DELETE FROM alembic_version WHERE version_num = '{BAD_VERSION}'"))
                conn.commit()
                print(f"✓ Deleted bad version {BAD_VERSION}")
                
                # Verify
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                remaining_versions = [row[0] for row in result]
                print(f"Remaining versions: {remaining_versions}")
                
                if len(remaining_versions) == 1 and remaining_versions[0] == HEAD_VERSION:
                    print("✓ Database now correctly set to head version!")
                else:
                    print(f"⚠ Unexpected state: {remaining_versions}")
            else:
                print(f"Bad version {BAD_VERSION} not found (already cleaned up?)")
        else:
            print(f"✗ Head version {HEAD_VERSION} not found in database")
            
except Exception as e:
    print(f"Error: {e}")
    exit(1)