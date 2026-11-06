from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT style, COUNT(*) as count
        FROM clothing_items
        GROUP BY style
        ORDER BY count DESC
    """)).fetchall()
    
    print('📊 STYLES dans votre garde-robe:')
    for row in result:
        style = row[0] if row[0] else "(vide/NULL)"
        print(f'   {style}: {row[1]} pièces')
