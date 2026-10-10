import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all models on Base.metadata
from app.agents import metadata_agent as metadata_module
from app.agents.context_agent import ContextAgent
from app.agents.metadata_agent import MetadataAgent
from app.agents.orchestrator import AgentOrchestrator
from app.agents.packing_agent import PackingAgent
from app.api.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.clothing_item import ClothingItem
from app.models.scheduled_outfit import ScheduledOutfit
from app.models.user import User
from app.services import seasons


# --- seasons service -------------------------------------------------------------

def test_normalize_season_accepts_app_and_english_words():
    assert seasons.normalize_season("Été") == "ete"
    assert seasons.normalize_season("winter") == "hiver"
    assert seasons.normalize_season("printemps") == "mi_saison"
    assert seasons.normalize_season("n'importe quoi") is None
    assert seasons.normalize_season(None) is None


def test_trip_season_uses_weather_only_for_near_trips():
    today = date(2026, 7, 1)  # summer by the calendar

    assert seasons.trip_season(today + timedelta(days=2), 5.0, today=today) == "hiver"  # near: cold weather wins
    assert seasons.trip_season(today + timedelta(days=100), 5.0, today=today) == "mi_saison"  # far (Oct 9): calendar, not weather
    assert seasons.trip_season(date(2027, 1, 10), 30.0, today=today) == "hiver"
    assert seasons.trip_season(None, None, today=today) == "ete"


def test_season_compatible_is_permissive_for_unknown_and_all_seasons():
    assert seasons.season_compatible(None, "hiver")
    assert seasons.season_compatible("toutes_saisons", "hiver")
    assert seasons.season_compatible("hiver", "hiver")
    assert not seasons.season_compatible("ete", "hiver")
    assert seasons.season_compatible("ete", None)


# --- context agent ---------------------------------------------------------------

def test_context_infers_season_from_temperature_and_normalizes_explicit(monkeypatch):
    monkeypatch.setattr(
        "app.agents.context_agent.WeatherService.get_current_weather",
        lambda self, city: {"weather": [{"description": "clear"}], "main": {"temp": 31.0}},
    )

    assert ContextAgent().run(city="Tunis")["season"] == "ete"
    assert ContextAgent().run(city="Tunis", season="automne")["season"] == "mi_saison"


# --- packing agent ---------------------------------------------------------------

class _Item:
    def __init__(self, category="haut", style="Casual", season=None):
        self.id = uuid.uuid4()
        self.category, self.style, self.season = category, style, season


def test_packing_prefers_season_compatible_items():
    summer, winter = _Item(season="ete"), _Item(season="hiver")

    result = PackingAgent().run(
        wardrobe_items=[winter, summer], duration_days=1, trip_type="tourisme", season="ete"
    )

    assert result["item_ids"] == [summer.id]


def test_packing_skips_veste_in_summer_even_for_tourism():
    veste = _Item("veste", season="toutes_saisons")

    assert PackingAgent().run(
        wardrobe_items=[veste], duration_days=3, trip_type="tourisme", season="ete"
    )["item_ids"] == []
    assert PackingAgent().run(
        wardrobe_items=[veste], duration_days=3, trip_type="tourisme", season="hiver"
    )["item_ids"] == [veste.id]


def test_packing_rotates_away_from_most_worn_items():
    worn_a_lot, fresh = _Item(), _Item()
    usage = {worn_a_lot.id: {"wear_count": 9, "last_worn": date(2026, 10, 1)}}

    result = PackingAgent().run(
        wardrobe_items=[worn_a_lot, fresh], duration_days=1, trip_type="tourisme", usage=usage
    )

    assert result["item_ids"] == [fresh.id]


def test_packing_always_includes_required_items_beyond_the_quota():
    items = [_Item() for _ in range(3)]
    required = {items[2].id}

    result = PackingAgent().run(
        wardrobe_items=items, duration_days=1, trip_type="tourisme", required_item_ids=required
    )

    assert result["item_ids"] == [items[2].id]  # quota is 1, and that slot goes to the planned piece


# --- metadata agent + orchestrator on a real (sqlite) schema ----------------------

@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(metadata_module.vector_store, "upsert_item_embedding", lambda *a, **k: None)
    monkeypatch.setattr(metadata_module.vector_store, "delete_item_embedding", lambda *a, **k: None)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


@pytest.fixture
def user(db):
    u = User(email="a@b.c", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _add(db, user, **fields):
    item = ClothingItem(owner_id=user.id, image_url="u", **fields)
    db.add(item)
    db.commit()
    return item


def test_wearable_in_filter(db, user):
    summer = _add(db, user, category="haut", season="ete")
    _add(db, user, category="haut", season="hiver")
    anytime = _add(db, user, category="haut", season="toutes_saisons")

    ids = {i.id for i in MetadataAgent(db).run(user_id=user.id, wearable_in="ete")["items"]}

    assert ids == {summer.id, anytime.id}


def test_log_worn_is_idempotent_and_not_double_counted_with_calendar(db, user):
    item = _add(db, user, category="haut")
    agent = MetadataAgent(db)
    day = date(2026, 10, 5)
    db.add(ScheduledOutfit(owner_id=user.id, date=day, item_ids=[item.id]))
    db.commit()

    assert agent.log_worn(user_id=user.id, item_id=item.id, day=day)  # same day as the plan
    assert agent.log_worn(user_id=user.id, item_id=item.id, day=day)  # twice
    assert agent.log_worn(user_id=user.id, item_id=item.id, day=date(2026, 10, 7))

    history = agent.usage_history(user_id=user.id, today=date(2026, 10, 10))
    assert history[item.id] == {"wear_count": 2, "last_worn": date(2026, 10, 7)}


def test_log_worn_rejects_foreign_items(db, user):
    other = User(email="d@e.f", hashed_password="x")
    db.add(other)
    db.commit()
    foreign = _add(db, other, category="haut")

    assert MetadataAgent(db).log_worn(user_id=user.id, item_id=foreign.id) is False


def test_plan_trip_packs_planned_outfits_and_stores_season(db, user, monkeypatch):
    monkeypatch.setattr(
        "app.agents.context_agent.WeatherService.get_current_weather", lambda self, city: None
    )
    pieces = [_add(db, user, category="haut", season="ete") for _ in range(4)]
    planned = pieces[3]
    start = date.today() + timedelta(days=60)
    db.add(ScheduledOutfit(owner_id=user.id, date=start, item_ids=[planned.id]))
    db.commit()

    packing = AgentOrchestrator(db).plan_trip(
        user_id=user.id, destination="Tunis", duration_days=2, trip_type="tourisme", start_date=start
    )

    assert planned.id in packing.item_ids
    assert packing.start_date == start
    assert packing.season == seasons.season_for_date(start)
    assert len(packing.item_ids) == 2  # one top per day


# --- HTTP routes ------------------------------------------------------------------

@pytest.fixture
def client(db, user):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_wardrobe_filters_by_query_params(client, db, user):
    _add(db, user, category="haut", colors=["bleu"], season="ete")
    _add(db, user, category="bas", colors=["noir"], season="hiver")

    everything = client.get("/api/v1/wardrobe/").json()
    only_bas = client.get("/api/v1/wardrobe/", params={"category": "bas"}).json()
    by_text = client.get("/api/v1/wardrobe/", params={"q": "bleu"}).json()
    by_season = client.get("/api/v1/wardrobe/", params={"season": "hiver"}).json()

    assert len(everything) == 2
    assert [i["category"] for i in only_bas] == ["bas"]
    assert [i["category"] for i in by_text] == ["haut"]
    assert [i["category"] for i in by_season] == ["bas"]


def test_worn_endpoint_then_usage_endpoint(client, db, user):
    item = _add(db, user, category="haut")

    first = client.post(f"/api/v1/wardrobe/{item.id}/worn")
    usage = client.get("/api/v1/wardrobe/usage").json()

    assert first.status_code == 200 and first.json()["wear_count"] == 1
    assert usage == [{"item_id": str(item.id), "wear_count": 1, "last_worn": date.today().isoformat()}]


def test_worn_endpoint_rejects_future_day_and_unknown_item(client, db, user):
    item = _add(db, user, category="haut")
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    assert client.post(f"/api/v1/wardrobe/{item.id}/worn", json={"day": tomorrow}).status_code == 422
    assert client.post(f"/api/v1/wardrobe/{uuid.uuid4()}/worn").status_code == 404


def test_packing_route_accepts_start_date_and_returns_season(client, db, user, monkeypatch):
    monkeypatch.setattr(
        "app.agents.context_agent.WeatherService.get_current_weather", lambda self, city: None
    )
    _add(db, user, category="haut", season="hiver")

    response = client.post(
        "/api/v1/packing/",
        json={"destination": "Tunis", "duration_days": 1, "trip_type": "tourisme", "start_date": "2027-01-15"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["season"] == "hiver" and body["start_date"] == "2027-01-15"
    assert len(body["items"]) == 1
