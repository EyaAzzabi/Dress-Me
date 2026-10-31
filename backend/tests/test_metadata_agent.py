import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — registers all models on Base.metadata
from app.agents import metadata_agent as metadata_module
from app.agents.metadata_agent import MetadataAgent
from app.db.base import Base
from app.models.scheduled_outfit import ScheduledOutfit
from app.models.user import User


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


def _attrs(**over):
    base = {
        "category": "haut", "colors": ["noir"], "style": "Casual", "pattern": "uni",
        "season": "ete", "confidence": {"category": 0.9}, "embedding": None,
    }
    return {**base, **over}


def test_add_item_prefers_user_season_and_records_source(db, user):
    agent = MetadataAgent(db)

    user_chosen = agent.add_item(user_id=user.id, image_url="u", attributes=_attrs(), season="hiver")
    suggested = agent.add_item(user_id=user.id, image_url="u", attributes=_attrs())
    unsure = agent.add_item(user_id=user.id, image_url="u", attributes=_attrs(season=None))

    assert (user_chosen.season, user_chosen.season_source) == ("hiver", "user")
    assert (suggested.season, suggested.season_source) == ("ete", "vision")
    assert (unsure.season, unsure.season_source) == (None, None)
    assert suggested.attribute_confidence == {"category": 0.9}


def test_run_filters_and_searches(db, user):
    agent = MetadataAgent(db)
    agent.add_item(user_id=user.id, image_url="1", attributes=_attrs(colors=["bleu", "blanc"]))
    agent.add_item(user_id=user.id, image_url="2", attributes=_attrs(category="bas", colors=["noir"]))

    assert len(agent.run(user_id=user.id)["items"]) == 2
    assert [i.image_url for i in agent.run(user_id=user.id, category="bas")["items"]] == ["2"]
    assert [i.image_url for i in agent.run(user_id=user.id, color="blanc")["items"]] == ["1"]
    assert [i.image_url for i in agent.run(user_id=user.id, query="bleu casual")["items"]] == ["1"]
    assert agent.run(user_id=user.id, query="rouge")["items"] == []


def test_other_users_items_are_invisible(db, user):
    other = User(email="d@e.f", hashed_password="x")
    db.add(other)
    db.commit()
    agent = MetadataAgent(db)
    foreign = agent.add_item(user_id=other.id, image_url="x", attributes=_attrs())

    assert agent.run(user_id=user.id)["items"] == []
    assert agent.update_item(user_id=user.id, item_id=foreign.id, changes={"style": "Formal"}) is None
    assert agent.remove_item(user_id=user.id, item_id=foreign.id) is False


def test_usage_history_counts_past_planned_days_only(db, user):
    agent = MetadataAgent(db)
    a = agent.add_item(user_id=user.id, image_url="a", attributes=_attrs())
    b = agent.add_item(user_id=user.id, image_url="b", attributes=_attrs())
    for day, ids in [
        (date(2026, 10, 1), [a.id]), (date(2026, 10, 5), [a.id, b.id]), (date(2026, 10, 20), [a.id]),
    ]:
        db.add(ScheduledOutfit(owner_id=user.id, date=day, item_ids=ids))
    db.commit()

    history = agent.usage_history(user_id=user.id, today=date(2026, 10, 10))

    assert history[a.id] == {"wear_count": 2, "last_worn": date(2026, 10, 5)}
    assert history[b.id] == {"wear_count": 1, "last_worn": date(2026, 10, 5)}
    assert uuid.uuid4() not in history
