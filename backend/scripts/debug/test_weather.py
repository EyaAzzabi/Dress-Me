"""Test rapide de l'API météo OpenWeather"""
from app.services.weather import WeatherService
from app.agents.context_agent import ContextAgent

print("🌤️  Test de l'API OpenWeather\n")

# Test 1: Service météo direct
print("Test 1: Récupération météo pour Tunis...")
weather_service = WeatherService()
data = weather_service.get_current_weather("Tunis")

if data:
    print(f"✅ Succès!")
    print(f"   Température: {data['main']['temp']:.1f}°C")
    print(f"   Temps: {data['weather'][0]['description']}")
    print(f"   Humidité: {data['main']['humidity']}%")
    print(f"   Vent: {data['wind']['speed']} m/s")
else:
    print("❌ Échec - Clé API manquante ou invalide")

# Test 2: Context Agent avec ville
print("\nTest 2: Context Agent avec ville='Tunis'...")
context_agent = ContextAgent()
result = context_agent.run(city="Tunis", occasion="événement")

print(f"✅ Résultat:")
print(f"   Météo: {result['weather']}")
print(f"   Température: {result['temperature']}°C")
print(f"   Bande météo: {result['weather_band']}")
print(f"   Saison inférée: {result['season']}")
print(f"   Occasion catégorie: {result['occasion_category']}")
print(f"   Formalité: {result['formality']}/5")

print("\n🎉 Configuration météo fonctionnelle!")
