"""Season vocabulary shared by the wardrobe, packing and recommendations.

Items use ete / hiver / mi_saison / toutes_saisons (see ClothingItem.season). Callers
may also pass the looser words the apps send (été, printemps, automne, summer, ...),
so everything is normalized here once. Date-based seasons assume the northern
hemisphere (DressMe targets Tunisia) — a rule, not a lookup by destination.
"""

from datetime import date, timedelta

SEASON_ALIASES = {
    "ete": "ete", "été": "ete", "summer": "ete",
    "hiver": "hiver", "winter": "hiver",
    "mi_saison": "mi_saison", "mi-saison": "mi_saison",
    "printemps": "mi_saison", "spring": "mi_saison",
    "automne": "mi_saison", "autumn": "mi_saison", "fall": "mi_saison",
}

COLD_BELOW_C = 14.0
HOT_FROM_C = 24.0
# A trip starting this soon is better judged by the destination's current weather
# than by the calendar; further out, current weather says nothing about the trip.
WEATHER_HORIZON_DAYS = 5


def normalize_season(value: str | None) -> str | None:
    """'Été' / 'summer' -> 'ete'; None or an unknown word -> None."""
    if not value:
        return None
    return SEASON_ALIASES.get(value.strip().lower())


def season_for_date(day: date) -> str:
    if day.month in (12, 1, 2):
        return "hiver"
    if day.month in (6, 7, 8):
        return "ete"
    return "mi_saison"


def season_from_temperature(temp_c: float) -> str:
    if temp_c < COLD_BELOW_C:
        return "hiver"
    if temp_c >= HOT_FROM_C:
        return "ete"
    return "mi_saison"


def trip_season(start_date: date | None, temperature_c: float | None, today: date | None = None) -> str:
    """Season to pack for. Near-term trips use the destination's current temperature
    when we have it; otherwise the start date (or today when no date was given)."""
    today = today or date.today()
    if temperature_c is not None and (
        start_date is None or start_date <= today + timedelta(days=WEATHER_HORIZON_DAYS)
    ):
        return season_from_temperature(temperature_c)
    return season_for_date(start_date or today)


def season_compatible(item_season: str | None, target: str | None) -> bool:
    """Can an item be worn in the target season? Unknown on either side is
    permissive — don't hide a piece just because nobody labeled it."""
    item_season = normalize_season(item_season) or item_season
    if target is None or item_season is None or item_season == "toutes_saisons":
        return True
    return item_season == target
