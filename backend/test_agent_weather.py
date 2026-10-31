"""
Vérifie quelle météo reçoit le RecommendationAgent quand on appelle /recommendations/outfits
"""
from dotenv import load_dotenv; load_dotenv()
from app.agents.context_agent import ContextAgent

agent = ContextAgent()

# Simule un appel avec city=Tunis (comme le frontend)
ctx = agent.run(city="Tunis", occasion="quotidien", season=None, weather=None)

print("=== Contexte météo reçu par l'agent ===")
print(f"  weather      : {ctx.get('weather')}")
print(f"  temperature  : {ctx.get('temperature')}°C")
print(f"  weather_band : {ctx.get('weather_band')}")
print(f"  season       : {ctx.get('season')}")
print(f"  occasion_cat : {ctx.get('occasion_category')}")
