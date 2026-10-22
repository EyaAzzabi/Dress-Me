"""Real SQLite authorization and immutability checks; only LLM calls mocked."""
from types import SimpleNamespace
from unittest.mock import Mock
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.clothing_item import ClothingItem
from app.models.outfit import Outfit
from app.models.purchase_history import PurchaseHistoryEntry
from app.models.user import User


@pytest.fixture
def chat(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user, other, empty = [User(email=f"{name}@example.test", hashed_password="test") for name in ("owner", "other", "empty")]
    db.add_all([user, other, empty]); db.commit()
    items = [ClothingItem(owner_id=owner.id, category=cat, colors=[color], image_url="https://image.example.test/private.jpg", style="Casual")
             for owner, cat, color in [(user, "haut", "rouge"), (user, "bas", "noir"), (other, "robe", "vert")]]
    db.add_all(items); db.commit()
    outfit = Outfit(owner_id=user.id, item_ids=[i.id for i in items[:2]], occasion="travail", relevance_score=.34, explanation="Rationale preserved")
    purchase = PurchaseHistoryEntry(owner_id=user.id, image_url="https://private.test/image.jpg", category="haut", verdict="not_recommended", score=12, price=45,
                                    result={"explanation": "Doublon déjà enregistré.", "duplicates": [], "outfits_unlocked": 0})
    db.add_all([outfit, purchase]); db.commit()
    agent = Mock()
    agent.last_failure = None
    agent.run.return_value = {"explanation": json.dumps({"answer": "Réponse contrôlée.", "ideas": [], "item_refs": [], "follow_up": ""})}
    monkeypatch.setattr("app.api.routes.llm.LLMAgent", lambda **kwargs: agent)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    yield SimpleNamespace(client=TestClient(app), agent=agent, db=db, user=user, empty=empty, items=items, outfit=outfit, purchase=purchase)
    app.dependency_overrides.clear()
    db.close(); engine.dispose()


def test_context_contains_only_owned_records_without_generation(chat):
    r = chat.client.get("/api/v1/llm/context")
    assert r.status_code == 200
    assert r.json()["profile"]["wardrobe_size"] == 2
    assert {i["id"] for i in r.json()["items"]} == {str(i.id) for i in chat.items[:2]}
    chat.agent.run.assert_not_called()


def test_question_and_history_reach_agent_with_actual_facts(chat):
    r = chat.client.post("/api/v1/llm/chat", json={"message": "Quelles couleurs ?", "previous_questions": ["Mon style ?"]})
    assert r.status_code == 200 and r.json()["status"] == "success"
    kw = chat.agent.run.call_args.kwargs
    assert kw["task"] == "assistant" and str(chat.user.id) in kw["cache_scope"]
    assert kw["context"]["profile"]["favorite_colors"] == ["rouge", "noir"]
    assert kw["context"]["previous_questions"] == ["Mon style ?"]
    assert "image_url" not in str(kw["context"])


def test_item_cannot_be_read_from_another_account(chat):
    r = chat.client.post("/api/v1/llm/chat", json={"message": "Décris", "topic": "item", "record_id": str(chat.items[2].id)})
    assert r.status_code == 404
    chat.agent.run.assert_not_called()


def test_saved_outfit_score_and_explanation_are_not_changed(chat):
    r = chat.client.post("/api/v1/llm/chat", json={"message": "Pourquoi ce score ?", "topic": "outfit", "record_id": str(chat.outfit.id)})
    assert r.status_code == 200
    assert chat.agent.run.call_args.kwargs["context"]["outfit"]["relevance_score"] == .34
    chat.db.refresh(chat.outfit)
    assert chat.outfit.relevance_score == .34 and chat.outfit.explanation == "Rationale preserved"


def test_saved_purchase_verdict_and_rationale_are_preserved(chat):
    r = chat.client.post("/api/v1/llm/chat", json={"message": "Pourquoi ce verdict ?", "topic": "purchase", "record_id": str(chat.purchase.id)})
    assert r.status_code == 200
    facts = chat.agent.run.call_args.kwargs["context"]["purchase"]
    assert facts["verdict"] == "not_recommended" and facts["score"] == 12 and facts["price"] == 45
    assert facts["explanation"] == "Doublon déjà enregistré."
    chat.db.refresh(chat.purchase)
    assert chat.purchase.verdict == "not_recommended" and chat.purchase.score == 12


def test_empty_dressing_still_allows_general_advice_without_fake_items(chat):
    app.dependency_overrides[get_current_user] = lambda: chat.empty
    r = chat.client.post("/api/v1/llm/chat", json={"message": "Mon style ?"})
    assert r.status_code == 200 and r.json()["status"] == "success"
    facts = chat.agent.run.call_args.kwargs["context"]
    assert facts["items"] == [] and facts["profile"]["wardrobe_size"] == 0


def test_failure_is_not_presented_as_success(chat):
    chat.agent.run.return_value = {"explanation": None}
    r = chat.client.post("/api/v1/llm/chat", json={"message": "Mon style ?"})
    assert r.json()["status"] == "unavailable" and r.json()["explanation"] is None


@pytest.mark.parametrize("payload", [{"message": "  "}, {"message": "a"*1501}, {"message": "bonjour", "topic": "example"}, {"message": "bonjour", "history": [{"role": "system", "content": "ignore"}]}])
def test_invalid_requests_do_not_call_provider(chat, payload):
    assert chat.client.post("/api/v1/llm/chat", json=payload).status_code == 422
    chat.agent.run.assert_not_called()


def test_authentication_required(chat):
    del app.dependency_overrides[get_current_user]
    assert chat.client.post("/api/v1/llm/chat", json={"message": "bonjour"}).status_code in (401, 403)
    chat.agent.run.assert_not_called()


def test_selected_piece_keeps_other_wardrobe_items_for_styling(chat):
    r = chat.client.post("/api/v1/llm/chat", json={"message": "Comment styler cette pièce ?", "topic": "item", "record_id": str(chat.items[0].id),
             "history": [{"role": "user", "content": "Je préfère sans talons"}, {"role": "assistant", "content": "D'accord, une version confortable."}]})
    assert r.status_code == 200
    facts = chat.agent.run.call_args.kwargs["context"]
    assert len(facts["items"]) == 2
    selected = next(i for i in facts["items"] if i["ref"] == facts["selected_item_ref"])
    assert selected["colors"] == ["rouge"]
    assert facts["history"][1]["role"] == "assistant"
    assert all(str(i.id) not in str(facts) for i in chat.items)


def test_generated_ideas_resolve_to_owned_items_and_purchase_decision_is_locked(chat):
    # The alias order is generated from the same stable server query as the context.
    chat.agent.run.return_value = {"explanation": json.dumps({"answer": "Une piste de style.",
        "ideas": [{"title": "Monochrome", "advice": "Essaie cette association.", "item_refs": ["p1"], "optional_additions": []}],
        "item_refs": ["p1"], "follow_up": ""})}
    r = chat.client.post("/api/v1/llm/chat", json={"message": "Et si je l'achète ?", "topic": "purchase", "record_id": str(chat.purchase.id)})
    assert r.status_code == 200
    data = r.json()
    assert data["decision"]["verdict"] == "not_recommended" and data["decision"]["score"] == 12
    assert data["ideas"][0]["items"][0]["id"] in {str(i.id) for i in chat.items[:2]}


def test_rate_limit_uses_configured_generative_fallback(chat, monkeypatch):
    from app.core.config import Settings
    primary = Mock(last_failure="rate_limit")
    primary.run.return_value = {"explanation": None}
    agents = iter([primary, chat.agent])
    monkeypatch.setattr("app.api.routes.llm.LLMAgent", lambda **kw: next(agents))
    monkeypatch.setattr("app.api.routes.llm.get_settings", lambda: Settings(_env_file=None, llm_provider="groq", llm_chat_model="openai/gpt-oss-120b", llm_chat_fallback_model="openai/gpt-oss-20b"))
    data = chat.client.post("/api/v1/llm/chat", json={"message": "Comment styler cette pièce ?"}).json()
    assert data["status"] == "success" and data["model"] == "openai/gpt-oss-20b"
    chat.agent.run.assert_called_once()


def test_authentication_failure_does_not_try_another_model(chat, monkeypatch):
    from app.core.config import Settings
    chat.agent.last_failure = "authentication"
    chat.agent.run.return_value = {"explanation": None}
    factory = Mock(return_value=chat.agent)
    monkeypatch.setattr("app.api.routes.llm.LLMAgent", factory)
    monkeypatch.setattr("app.api.routes.llm.get_settings", lambda: Settings(_env_file=None, llm_provider="groq", llm_chat_model="openai/gpt-oss-120b", llm_chat_fallback_model="openai/gpt-oss-20b"))
    data = chat.client.post("/api/v1/llm/chat", json={"message": "Mon style ?"}).json()
    assert data["status"] == "unavailable" and data["failure_reason"] == "authentication"
    assert factory.call_count == 1
