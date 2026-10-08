"""
Create all tables in the SQLite database directly via SQLAlchemy metadata.
Run once before starting the server: python init_db.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401 — registers all models on Base.metadata

Base.metadata.create_all(bind=engine)
print("✅ Database tables created successfully.")
