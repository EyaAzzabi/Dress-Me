"""Test des explications Mistral une fois configuré"""
from app.agents.llm_agent import LLMAgent
from app.agents.recommendation_agent import _build_explanation
from app.models.clothing_item import ClothingItem

print("🤖 Test des explications avec LLM\n")

# Simuler des items de vêtements
class MockItem:
    def __init__(self, category, season=None, colors=None, style=None):
        self.category = category
        self.season = season
        self.colors = colors or []
        self.style = style

outfit = [
    MockItem("haut", season="mi_saison", colors=["rose"], style="Casual"),
    MockItem("bas", season="hiver", colors=["noir"], style="Casual"),
    MockItem("chaussures", season="toutes_saisons", colors=["blanc"], style="Sports"),
    MockItem("sac", season="toutes_saisons", colors=["marron"]),
    MockItem("accessoire", colors=["doré"]),
]

# Test avec LLMAgent
llm_agent = LLMAgent()

print("1. Test du parsing d'occasion:")
print("-" * 50)
result = llm_agent.parse_occasion(
    "je vais à un mariage ce soir", 
    {"season": "été", "weather": "sunny, 28°C"}
)
if result:
    print(f"✅ Parsing réussi:")
    print(f"   Catégorie: {result['occasion_category']}")
    print(f"   Formalité: {result['formality']}/5")
    print(f"   Dress code: {result.get('dress_code')}")
else:
    print("⚠️  LLM désactivé (provider=none) - parsing via règles déterministes")

print("\n2. Test d'explication de tenue:")
print("-" * 50)

explanation = _build_explanation(
    llm_agent=llm_agent,
    outfit=outfit,
    score=0.59,
    occasion="événement",
    style_match=False,
    top_style="Casual",
    season="mi_saison",
    weather="partly cloudy, 22°C",
    occasion_category="casual_quotidien",
    formality=2,
    temperature=22.0,
    weather_band="modere",
    references=None
)

print(f"Explication générée:")
print(f"   {explanation}")

if "Loose match" in explanation:
    print("\n⚠️  LLM désactivé - utilise template déterministe")
    print("\n📝 Pour activer Mistral:")
    print("   1. Obtiens une clé API sur https://console.mistral.ai/")
    print("   2. Ajoute dans .env:")
    print("      LLM_PROVIDER=mistral")
    print("      LLM_API_KEY=ta-clé-ici")
    print("   3. Redémarre le backend")
else:
    print("\n✅ LLM activé - explication riche générée!")

print("\n" + "="*50)
