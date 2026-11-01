#!/usr/bin/env python
"""Test password hashing and verification."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.models.user import User

def test_password():
    """Test password hashing and verification."""
    settings = get_settings()
    
    # Create engine and session
    is_sqlite = "sqlite" in settings.database_url
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False} if is_sqlite else {}
    )
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Get the test user
        user = session.query(User).filter(User.email == "test@test.com").first()
        if not user:
            print("✗ Test user not found")
            return
        
        print(f"✓ Found user: {user.email}")
        print(f"  Hashed password: {user.hashed_password[:50]}...")
        
        # Test verification
        test_password = "password123"
        is_valid = verify_password(test_password, user.hashed_password)
        print(f"  verify_password('{test_password}', hash): {is_valid}")
        
        if is_valid:
            print("✓ Password verification works!")
        else:
            print("✗ Password verification failed!")
            # Try to hash and verify a fresh password
            print("\n  Testing fresh hash:")
            fresh_hash = hash_password("password123")
            print(f"  Fresh hash: {fresh_hash[:50]}...")
            is_valid_fresh = verify_password("password123", fresh_hash)
            print(f"  verify_password('password123', fresh_hash): {is_valid_fresh}")
        
    finally:
        session.close()

if __name__ == "__main__":
    test_password()
