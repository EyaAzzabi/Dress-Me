#!/usr/bin/env python
"""Test the complete login flow."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
from app.core.security import verify_password
from app.models.user import User
from app.db.session import get_db, SessionLocal

def test_login():
    """Test login flow."""
    settings = get_settings()
    print(f"Database: {settings.database_url}")
    
    try:
        # Get a session the same way the API does
        session = SessionLocal()
        
        # Query the user
        user = session.query(User).filter(User.email == "test@test.com").first()
        print(f"User found: {user is not None}")
        
        if user:
            print(f"  Email: {user.email}")
            print(f"  ID: {user.id}")
            print(f"  Hash: {user.hashed_password[:50]}...")
            
            # Test password
            pwd = "password123"
            is_valid = verify_password(pwd, user.hashed_password)
            print(f"  Password '{pwd}' valid: {is_valid}")
            
            if is_valid:
                print("LOGIN SUCCESS")
            else:
                print("LOGIN FAILED - password mismatch")
        else:
            print("LOGIN FAILED - user not found")
        
        session.close()
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_login()
