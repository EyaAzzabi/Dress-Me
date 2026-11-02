from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))

user_id = 'f438dfec-2686-4459-9bb6-204b5b756de0'

with engine.connect() as conn:
    # Test filtre saison
    all_items = conn.execute(text('''
        SELECT COUNT(*) FROM clothing_items WHERE owner_id = :uid
    '''), {'uid': user_id}).scalar()
    
    spring_items = conn.execute(text('''
        SELECT COUNT(*) FROM clothing_items 
        WHERE owner_id = :uid
        AND (season = 'spring' OR season = 'toutes_saisons' OR season IS NULL)
    '''), {'uid': user_id}).scalar()
    
    print(f'📊 FILTERING TEST:')
    print(f'  Total items: {all_items}')
    print(f'  Spring-compatible items: {spring_items}')
    print()
    
    if spring_items == 0:
        print('❌ PROBLÈME: Zéro item compatible spring!')
        print('   Distribution des saisons:')
        
        items = conn.execute(text('''
            SELECT season, COUNT(*) FROM clothing_items 
            WHERE owner_id = :uid
            GROUP BY season
        '''), {'uid': user_id}).fetchall()
        
        for season, count in items:
            season_label = season if season else "(NULL/pas de saison)"
            print(f'     {season_label}: {count}')
