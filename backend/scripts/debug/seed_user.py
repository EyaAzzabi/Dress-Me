#!/usr/bin/env python
"""Create a test user for development."""

import sys
from pathlib import Path
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
from app.models.user import User
from app.core.security import hash_password

def seed_test_user():
    """Create a test user."""
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
        # Check if test user already exists
        existing = session.query(User).filter(User.email == "test@test.com").first()
        if existing:
            print(f"✓ Test user already exists: {existing.email}")
            return
        
        # Create test user
        test_user = User(
            id=uuid.uuid4(),
            email="test@test.com",
            hashed_password=hash_password("password123"),
            full_name="Test User"
        )
        
        session.add(test_user)
        session.commit()
        
        print(f"✓ Test user created: {test_user.email}")
        print(f"  ID: {test_user.id}")
        print(f"  Credentials: test@test.com / password123")
        
    except Exception as e:
        session.rollback()
        print(f"✗ Error creating user: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    seed_test_user()
