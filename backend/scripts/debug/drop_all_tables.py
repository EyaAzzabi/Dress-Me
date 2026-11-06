"""Script pour supprimer toutes les tables"""
from app.db.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    # Supprimer toutes les tables
    conn.execute(text('DROP SCHEMA public CASCADE'))
    conn.execute(text('CREATE SCHEMA public'))
    conn.commit()
    print('✅ Toutes les tables ont été supprimées')
    print('Maintenant exécutez: alembic upgrade head')
