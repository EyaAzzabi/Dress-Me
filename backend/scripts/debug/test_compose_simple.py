import sys
sys.path.insert(0, '.')
from app.agents.recommendation_agent_v2 import RecommendationAgentV2

class MockItem:
    def __init__(self, id, cat):
        self.id = id
        self.category = cat

items = [
    MockItem('1', 'haut'), MockItem('2', 'haut'),
    MockItem('3', 'bas'), MockItem('4', 'bas'),
    MockItem('5', 'chaussures'), MockItem('6', 'chaussures'),
]

agent = RecommendationAgentV2()
scores = {str(i.id): 0.8 for i in items}

outfits = agent._compose_outfit_candidates(items, scores, top_k=3)

print(f'✅ {len(outfits)} outfits générés')
for i, outfit in enumerate(outfits):
    cats = [item.category for item in outfit]
    print(f'  Outfit {i+1}: {len(outfit)} items - {cats}')
