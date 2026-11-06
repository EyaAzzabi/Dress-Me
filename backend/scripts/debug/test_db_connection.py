#!/usr/bin/env python
"""Test Supabase connection"""

from sqlalchemy import create_engine, text
import os

db_url = "postgresql+psycopg://postgres.fpuudgbekppqbjtwmowm:f&d$M2gaTB8q4Kt@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

print("Testing Supabase connection...")
print(f"URL: {db_url[:50]}...")

try:
    engine = create_engine(
        db_url, 
        echo=False, 
        pool_pre_ping=True, 
        connect_args={"connect_timeout": 10, "application_name": "dressme-test"},
        pool_size=2,
        max_overflow=0
    )
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("[OK] Supabase connection successful!")
        print(f"Query result: {result.fetchone()}")
        
except Exception as e:
    print(f"[ERROR] Connection failed: {str(e)[:300]}")
    import traceback
    traceback.print_exc()
