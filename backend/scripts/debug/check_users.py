#!/usr/bin/env python
"""List all users in the database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings
from app.models.user import User

def check_users():
    """List all users."""
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
        users = session.query(User).all()
        print(f"Found {len(users)} user(s):")
        for u in users:
            print(f"  - {u.email} (id: {u.id})")
        
    finally:
        session.close()

if __name__ == "__main__":
    check_users()
