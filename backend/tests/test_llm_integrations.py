"""Real SQLite + orchestrator + scoring/HTTP contracts; only external I/O mocked."""
from copy import deepcopy
import json
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient
import httpx
import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.llm_agent import LLMAgent
from app.agents.orchestrator import AgentOrchestrator
from app.agents.purchase_agent import PurchaseAgent
from app.agents.style_profile_agent import StyleProfileAgent
from app.api.deps import get_current_user
from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.clothing_item import ClothingItem
from app.models.outfit import Outfit
from app.models.user import User
from app.schemas.outfit import PurchaseCheckResult
from app.services.llm_narratives import build_plan


@pytest.fixture
def system(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="llm@example.test", hashed_password="not-a-real-password")
    db.add(user)
    db.commit()
    items = [ClothingItem(owner_id=user.id, category=category, colors=[color], style="Casual",
                           season="toutes_saisons", image_url=f"https://images.test/{category}")
             for category, color in [("haut", "beige"), ("bas", "noir")]]
    db.add_all(items)
    db.commit()
    vector = np.zeros(512)
    vector[0] = 1
    embeddings = {str(i.id): vector.tolist() for i in items}
    monkeypatch.setattr("app.agents.orchestrator.vector_store.fetch_embeddings", lambda ids: embeddings)
    monkeypatch.setattr("app.agents.recommendation_agent.compatibility_model.pair_compatibility", lambda a, b: 0.8)
    monkeypatch.setattr("app.agents.context_agent.WeatherService.get_current_weather", lambda *a: None)
    monkeypatch.setattr("app.agents.purchase_agent.CatalogIndex.search", lambda *a, **k: [])
    monkeypatch.setattr("app.agents.purchase_agent.CatalogIndex.brand_affinity", lambda *a, **k: [])
    monkeypatch.setattr("app.agents.purchase_agent.EcommerceService.search_products", lambda *a, **k: [])
    settings = Settings(_env_file=None, llm_provider="groq", llm_api_key="integration-placeholder")
    monkeypatch.setattr("app.agents.llm_agent.get_settings", lambda: settings)
    LLMAgent.clear_cache()
    calls = []

    def post(url, **kw):
        payload = json.loads(kw["json"]["messages"][1]["content"])
        calls.append(payload)
        ordered = list(payload["required"]) + [f for f in payload["choices"] if f not in payload["required"]]
        content = json.dumps({"sentences": [{"fact": f, "variant": 0} for f in ordered]})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr("httpx.post", post)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield SimpleNamespace(db=db, user=user, items=items, settings=settings, calls=calls,
                          embeddings=embeddings, vector=vector, orchestrator=AgentOrchestrator(db),
                          client=TestClient(app))
    app.dependency_overrides.clear()
    LLMAgent.clear_cache()
    db.close()
    engine.dispose()


def test_profile_uses_actual_aggregates_and_reuses_cache_across_requests(system):
    a = StyleProfileAgent(system.db)
    result = a.run(user_id=system.user.id)
    assert result["wardrobe_size"] == 2
    assert "2 pièces" in result["narrative"] and "beige" in result["narrative"]
    assert "Casual" in result["narrative"]
    assert StyleProfileAgent(system.db).run(user_id=system.user.id) == result
    assert len(system.calls) == 1
    system.items[0].colors = ["bleu"]
    system.db.commit()
    changed = a.run(user_id=system.user.id)
    assert "bleu" in changed["narrative"] and "beige" not in changed["narrative"]
    assert len(system.calls) == 2


def test_profile_count_style_and_deletion_invalidate_cache(system):
    a = StyleProfileAgent(system.db)
    a.run(user_id=system.user.id)
    system.items[0].style = "Formal"
    system.db.commit()
    assert "Formal" in a.run(user_id=system.user.id)["narrative"]
    system.db.delete(system.items[1])
    system.db.commit()
    assert a.run(user_id=system.user.id)["wardrobe_size"] == 1
    assert len(system.calls) == 3


def test_profile_facts_only_path_avoids_generation(system):
    result = StyleProfileAgent(system.db).run(user_id=system.user.id, include_narrative=False)
    assert result["wardrobe_size"] == 2 and result["narrative"] is None
    assert not system.calls


def test_recommendation_keeps_selection_ranking_scores_and_api_schema(system):
    a = system.orchestrator
    original = a.recommendation_agent.run(wardrobe_items=system.items, occasion="mariage",
                                           favorite_styles=["Casual"], usage={})["outfits"]
    response = system.client.post("/api/v1/recommendations/outfits", json={"occasion": "mariage"})
    assert response.status_code == 200, response.text
    result = response.json()
    outfits = result["outfits"]
    assert [[str(i) for i in x["item_ids"]] for x in original] == [o["item_ids"] for o in outfits]
    assert [o["relevance_score"] for o in outfits] == [o["relevance_score"] for o in original]
    text = outfits[0]["explanation"]
    assert "haut (beige)" in text and "bas (noir)" in text and "mariage" in text
    assert "convient" not in text  # algorithm does not validate formality/dress code
    assert system.calls[0]["task"] == "outfit"  # no unused profile narrative request
    assert len(system.calls) == 1
    assert set(outfits[0]) == {"id", "item_ids", "occasion", "relevance_score", "explanation"}


def test_reused_outfits_refresh_current_context_score_and_explanation(system):
    a, user = system.orchestrator, system.user
    first = a.recommend_outfits(user_id=user.id, occasion="travail")["outfits"][0]
    identity = first.id
    text = first.explanation
    a.recommend_outfits(user_id=user.id, occasion="travail")
    assert len(system.calls) == 1
    first.relevance_score = -1  # simulate a stale persisted score
    system.db.commit()
    second = a.recommend_outfits(user_id=user.id, occasion="mariage", weather="pluie, 12°C", season="hiver")["outfits"][0]
    assert second.id == identity and system.db.query(Outfit).count() == 1
    assert second.relevance_score == 0.9
    assert second.occasion == "mariage" and second.explanation != text
    assert "travail" not in second.explanation and "pluie, 12°C" in second.explanation
    assert len(system.calls) == 2
    listed = system.client.get("/api/v1/recommendations/outfits").json()
    assert listed[0]["explanation"] == second.explanation
    assert len(system.calls) == 2  # historical list never regenerates


def test_changed_item_attributes_invalidate_outfit_explanation(system):
    a = system.orchestrator
    a.recommend_outfits(user_id=system.user.id)
    system.items[0].colors = ["vert"]
    system.db.commit()
    text = a.recommend_outfits(user_id=system.user.id)["outfits"][0].explanation
    assert "vert" in text and "beige" not in text
    assert len(system.calls) == 2


def test_absent_context_does_not_generate_weather_or_occasion(system):
    text = system.orchestrator.recommend_outfits(user_id=system.user.id)["outfits"][0].explanation
    assert "Météo" not in text and "Occasion" not in text and "Saison" not in text
    assert "mariage" not in text


def test_incoherent_style_cannot_claim_favorite_style_match(system):
    system.items[0].style = "Formal"
    system.db.commit()
    system.orchestrator.recommend_outfits(user_id=system.user.id)
    assert "style" not in system.calls[0]["choices"]


@pytest.mark.parametrize("mode", ["none", "429", "hallucination"])
def test_outfit_deterministic_fallback_replaces_stale_narrative(system, monkeypatch, mode):
    a = system.orchestrator
    original = a.recommend_outfits(user_id=system.user.id, occasion="travail")["outfits"][0]
    if mode == "none":
        system.settings.llm_provider = "none"
    else:
        def failing(url, **kw):
            if mode == "429":
                return httpx.Response(429, headers={"retry-after": "60"}, request=httpx.Request("POST", url))
            return httpx.Response(200, json={"choices": [{"message": {"content": "Une robe rouge à 99 TND"}}]},
                                  request=httpx.Request("POST", url))
        monkeypatch.setattr("httpx.post", failing)
    refreshed = a.recommend_outfits(user_id=system.user.id, occasion="soirée")["outfits"][0]
    assert refreshed.id == original.id
    assert "Strong visual match" in refreshed.explanation and "soirée" in refreshed.explanation
    assert "travail" not in refreshed.explanation and "99" not in refreshed.explanation


def _purchase_setup(system, monkeypatch):
    attrs = {"category": "haut", "colors": ["noir"], "style": "Casual", "pattern": "uni",
             "embedding": system.vector}
    monkeypatch.setattr("app.agents.orchestrator.VisionAgent.run", lambda self, **k: deepcopy(attrs))
    monkeypatch.setattr("app.agents.orchestrator.clothing_gate.is_clothing", lambda v: True)
    return attrs


def test_real_purchase_pipeline_changes_only_explanation_and_history_reuses_result(system, monkeypatch):
    attrs = _purchase_setup(system, monkeypatch)
    original = PurchaseAgent().run(attributes=attrs, wardrobe_items=system.items,
                                   embeddings=system.embeddings, price=59)
    result = system.orchestrator.evaluate_purchase(user_id=system.user.id, image_url="https://images.test/new", price=59)
    assert {k: v for k, v in result.items() if k != "explanation"} == {
            k: v for k, v in original.items() if k != "explanation"}
    assert result["verdict"] == "not_recommended"  # exact duplicate, computed upstream
    assert "similaire" in result["explanation"] and "59 TND" in result["explanation"]
    assert "besoin" in result["explanation"] and original["explanation"] in result["explanation"]
    PurchaseCheckResult(**result)
    payload = json.dumps(system.calls[0])
    assert "embedding" not in payload and "image_url" not in payload and str(system.user.id) not in payload
    response = system.client.post("/api/v1/purchase/check", json={"image_url": "https://images.test/new", "price": 59})
    assert response.status_code == 200, response.text
    call_count = len(system.calls)
    history = system.client.get("/api/v1/purchase/history").json()
    assert history[0]["result"]["explanation"] == response.json()["explanation"]
    assert len(system.calls) == call_count


@pytest.mark.parametrize("verdict", ["recommended", "think_twice", "not_recommended"])
def test_all_purchase_verdicts_immutable_and_mandatory(system, monkeypatch, verdict):
    _purchase_setup(system, monkeypatch)
    result = {"verdict": verdict, "score": 55, "compatibility_score": 0.55,
              "explanation": "Motif calculé par le moteur.", "item": {"category": "haut"},
              "outfits_unlocked": 2, "duplicates": [], "factors": []}
    snapshot = deepcopy(result)
    monkeypatch.setattr(system.orchestrator.purchase_agent, "run", lambda **kw: result)
    actual = system.orchestrator.evaluate_purchase(user_id=system.user.id, image_url="https://test")
    assert actual["verdict"] == verdict and actual["score"] == 55
    assert result == snapshot  # no mutation of upstream output
    assert "2 associations" in actual["explanation"]
    assert "price" not in system.calls[0]["choices"]
    assert "verdict" in system.calls[0]["required"]


def test_out_of_scope_purchase_skips_llm(system, monkeypatch):
    _purchase_setup(system, monkeypatch)
    monkeypatch.setattr("app.agents.orchestrator.clothing_gate.is_clothing", lambda v: False)
    result = system.orchestrator.evaluate_purchase(user_id=system.user.id, image_url="https://test")
    assert result["item"]["category"] == "hors_perimetre"
    assert not system.calls


def test_purchase_rejects_missing_verdict_and_falls_back(system, monkeypatch):
    attrs = _purchase_setup(system, monkeypatch)
    original = PurchaseAgent().run(attributes=attrs, wardrobe_items=system.items, embeddings=system.embeddings)
    monkeypatch.setattr("httpx.post", lambda url, **kw: httpx.Response(200,
        json={"choices": [{"message": {"content": '{"sentences":[{"fact":"policy","variant":0}]}'}}]},
        request=httpx.Request("POST", url)))
    actual = system.orchestrator.evaluate_purchase(user_id=system.user.id, image_url="https://test")
    assert actual == original


def test_no_evidence_is_not_invented_as_negative_purchase_evidence():
    plan = build_plan("purchase", {"verdict": "recommended", "outfits_unlocked": 0,
                      "explanation": "Ajoute tes vêtements pour une analyse personnalisée."})
    assert "outfits" not in plan.choices and "duplicates" not in plan.choices
    assert "price" not in plan.choices


def test_missing_outfit_attributes_are_never_inferred():
    plan = build_plan("outfit", {"items": [{"category": "haut"}, {"category": "bas", "colors": []}],
                                  "favorite_styles": ["minimaliste"], "context": {}})
    assert set(plan.choices) == {"composition"}
    assert "beige" not in json.dumps(plan.choices)
    assert "minimaliste" not in json.dumps(plan.choices)
