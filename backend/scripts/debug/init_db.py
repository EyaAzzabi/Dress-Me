#!/usr/bin/env python
"""Initialize SQLite database with all tables from ORM models."""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine, text
from app.core.config import get_settings

def init_db():
    """Create all tables in the database."""
    settings = get_settings()
    print(f"Using database: {settings.database_url}")
    
    # Create engine (SQLite will create the file if needed)
    is_sqlite = "sqlite" in settings.database_url
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False} if is_sqlite else {}
    )
    
    # For SQLite, disable foreign key constraints during creation, then enable
    if is_sqlite:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.commit()
    
    try:
        # Import models to register them
        import app.models  # noqa: F401
        from app.db.base import Base
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✓ Database tables created successfully")
        
        # Verify tables exist
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"✓ Tables created: {', '.join(tables)}")
    finally:
        if is_sqlite:
            with engine.connect() as conn:
                conn.execute(text("PRAGMA foreign_keys=ON"))
                conn.commit()

if __name__ == "__main__":
    init_db()
