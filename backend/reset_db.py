"""Script pour réinitialiser la base de données"""
from app.db.session import engine
from sqlalchemy import text

with engine.connect() as conn:
    # Supprimer la table de versions Alembic
    conn.execute(text('DROP TABLE IF EXISTS alembic_version'))
    conn.commit()
    print('✅ Table alembic_version supprimée')
    
print('Maintenant exécutez: alembic upgrade head')
