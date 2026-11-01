from fastapi import APIRouter

from app.api.routes import auth, calendar, llm, monitoring, packing, purchase, recommendations, style_profile, tryon, wardrobe, weather

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(wardrobe.router)
api_router.include_router(recommendations.router)
api_router.include_router(purchase.router)
api_router.include_router(style_profile.router)
api_router.include_router(llm.router)
api_router.include_router(calendar.router)
api_router.include_router(packing.router)
api_router.include_router(tryon.router)
api_router.include_router(weather.router)
api_router.include_router(monitoring.router)
