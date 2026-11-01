"""Offline tests for the Vision Agent's two-stage category and its type-based season/style.

No FashionCLIP and no real classifier: the pieces are stubbed so these run in milliseconds.
The real end-to-end quality is measured by ml/notebooks/13_vision_agent_evaluation.py.
"""

import json

import numpy as np
import pytest

from app.ml import garment_types, vision_model
from app.schemas.clothing_item import Season

EMBEDDING = np.ones(512) / np.sqrt(512)


# ---------------------------------------------------------------- the shipped priors artifact
def test_priors_artifact_is_well_formed():
    priors = json.loads(garment_types.PRIORS_PATH.read_text(encoding="utf-8"))

    assert len(priors["types"]) >= 30
    for row in priors["types"]:
        assert row["prompt"]
        assert sum(row["season"]) == pytest.approx(1.0, abs=2e-3)
        assert sum(row["usage"]) == pytest.approx(1.0, abs=2e-3)
        assert len(row["season"]) == len(priors["seasons"])
        assert len(row["usage"]) == len(priors["usages"])


def test_prior_seasons_are_valid_wardrobe_seasons():
    priors = json.loads(garment_types.PRIORS_PATH.read_text(encoding="utf-8"))
    allowed = set(Season.__args__)

    assert set(priors["seasons"]) <= allowed


def test_a_sweater_leans_away_from_summer_and_shorts_do_not(monkeypatch):
    priors = garment_types._priors()
    names = [t["article_type"] for t in priors["types"]]

    def one_hot(name):
        return lambda embedding: np.eye(len(names))[names.index(name)]

    monkeypatch.setattr(garment_types, "type_posterior", one_hot("Sweaters"))
    sweater = garment_types.season_posterior(EMBEDDING)
    monkeypatch.setattr(garment_types, "type_posterior", one_hot("Shorts"))
    shorts = garment_types.season_posterior(EMBEDDING)

    assert sweater["ete"] < 0.15 < shorts["ete"]
    assert sum(sweater.values()) == pytest.approx(1.0, abs=2e-3)


# ---------------------------------------------------------------- season / style thresholds
def test_season_is_only_suggested_when_confident(monkeypatch):
    monkeypatch.setattr(garment_types, "available", lambda: True)
    monkeypatch.setattr(garment_types, "season_posterior", lambda e: {"ete": 0.2, "hiver": 0.1, "mi_saison": 0.7})
    assert vision_model.predict_season(EMBEDDING)[0] == "mi_saison"

    monkeypatch.setattr(garment_types, "season_posterior", lambda e: {"ete": 0.45, "hiver": 0.1, "mi_saison": 0.45})
    label, confidence = vision_model.predict_season(EMBEDDING)
    assert label is None and confidence == pytest.approx(0.45)


def test_style_comes_from_the_four_learnable_styles(monkeypatch):
    monkeypatch.setattr(garment_types, "available", lambda: True)
    monkeypatch.setattr(garment_types, "usage_posterior", lambda e: {"Casual": 0.1, "Sports": 0.8, "Ethnic": 0.05, "Formal": 0.05})
    assert vision_model.predict_style(EMBEDDING)[0] == "Sports"

    monkeypatch.setattr(garment_types, "usage_posterior", lambda e: {"Casual": 0.4, "Sports": 0.3, "Ethnic": 0.2, "Formal": 0.1})
    assert vision_model.predict_style(EMBEDDING)[0] is None


def test_without_the_priors_artifact_season_and_style_fall_back_to_zero_shot(monkeypatch):
    monkeypatch.setattr(garment_types, "available", lambda: False)
    monkeypatch.setattr(
        garment_types, "season_posterior", lambda e: pytest.fail("priors must not be used when unavailable")
    )
    calls = []

    def fake_zero_shot(embedding, prompts, template):
        calls.append(tuple(prompts))
        return {name: (0.9 if i == 0 else 0.1 / (len(prompts) - 1)) for i, name in enumerate(prompts)}

    monkeypatch.setattr(vision_model, "_zero_shot_probs", fake_zero_shot)

    assert vision_model.predict_season(EMBEDDING)[0] == "ete"
    assert vision_model.predict_style(EMBEDDING)[0] == "Casual"
    assert len(calls) == 2


# ---------------------------------------------------------------- two-stage category
class _Probe:
    """Stands in for the 8-class probe (the 'is it clothing' gate)."""

    def __init__(self, label, confidence=0.9):
        self.label, self.confidence = label, confidence
        self.classes_ = np.array(["haut", "hors_perimetre"])

    def predict(self, x):
        return np.array([self.label])

    def predict_proba(self, x):
        return np.array([[self.confidence, 1 - self.confidence]])


class _Head:
    classes_ = np.array(["bas", "haut", "robe"])

    def __init__(self):
        self.asked = 0

    def predict_proba(self, x):
        self.asked += 1
        return np.array([[0.1, 0.2, 0.7]])


def test_non_clothing_never_reaches_the_garment_head(monkeypatch):
    head = _Head()
    monkeypatch.setattr(vision_model, "_load_category_classifier", lambda: _Probe("hors_perimetre", 0.8))
    monkeypatch.setattr(vision_model, "_load_garment_classifier", lambda: head)

    assert vision_model.predict_category(EMBEDDING) == ("hors_perimetre", 0.8)
    assert head.asked == 0


def test_garment_category_and_confidence_come_from_the_head(monkeypatch):
    monkeypatch.setattr(vision_model, "_load_category_classifier", lambda: _Probe("haut", 0.95))
    monkeypatch.setattr(vision_model, "_load_garment_classifier", lambda: _Head())

    label, confidence = vision_model.predict_category(EMBEDDING)

    assert label == "robe" and confidence == pytest.approx(0.7)


def test_category_falls_back_to_the_probe_without_the_head_artifact(monkeypatch):
    monkeypatch.setattr(vision_model, "_load_category_classifier", lambda: _Probe("haut", 0.66))
    monkeypatch.setattr(vision_model, "_load_garment_classifier", lambda: None)

    label, confidence = vision_model.predict_category(EMBEDDING)

    assert label == "haut" and confidence == pytest.approx(0.66)


def test_low_head_confidence_marks_the_category_uncertain(monkeypatch):
    monkeypatch.setattr(vision_model, "embed_image_bytes", lambda b: EMBEDDING)
    monkeypatch.setattr(vision_model, "predict_category", lambda e: ("robe", 0.55))
    monkeypatch.setattr(vision_model, "predict_colors", lambda e: (["noir"], 0.9))
    monkeypatch.setattr(vision_model, "predict_pattern", lambda e: ("uni", 0.8))
    monkeypatch.setattr(vision_model, "predict_style", lambda e: (None, 0.4))
    monkeypatch.setattr(vision_model, "predict_season", lambda e: (None, 0.4))

    result = vision_model.analyze_image(b"ignored")

    assert result["category_uncertain"] is True  # 0.55 < CATEGORY_MIN_CONFIDENCE (0.60)
    assert result["style"] is None and result["season"] is None


# ---------------------------------------------------------------- OpenAI style fill-in
def _stub_analysis(monkeypatch, style):
    monkeypatch.setattr(vision_model, "embed_image_bytes", lambda b: EMBEDDING)
    monkeypatch.setattr(vision_model, "predict_category", lambda e: ("haut", 0.9))
    monkeypatch.setattr(vision_model, "predict_colors", lambda e: (["noir"], 0.9))
    monkeypatch.setattr(vision_model, "predict_pattern", lambda e: ("uni", 0.8))
    monkeypatch.setattr(vision_model, "predict_style", lambda e: (style, 0.5))
    monkeypatch.setattr(vision_model, "predict_season", lambda e: (None, 0.4))


def test_openai_fills_only_a_missing_style(monkeypatch):
    from app.ml import vision_llm

    _stub_analysis(monkeypatch, None)
    monkeypatch.setattr(vision_llm, "available", lambda: True)
    monkeypatch.setattr(vision_llm, "describe_image", lambda b: {"style": "Sports", "category": "bas"})

    result = vision_model.analyze_image(b"x")

    assert result["style"] == "Sports" and result["style_source"] == "openai"
    assert result["category"] == "haut"  # category is never delegated


def test_openai_is_not_asked_when_fashionclip_already_has_a_style(monkeypatch):
    from app.ml import vision_llm

    _stub_analysis(monkeypatch, "Casual")
    monkeypatch.setattr(vision_llm, "available", lambda: True)
    monkeypatch.setattr(vision_llm, "describe_image", lambda b: pytest.fail("must not be called"))

    result = vision_model.analyze_image(b"x")

    assert result["style"] == "Casual" and result["style_source"] == "fashionclip"


def test_disabled_openai_is_never_called(monkeypatch):
    from app.ml import vision_llm

    _stub_analysis(monkeypatch, None)
    monkeypatch.setattr(vision_llm, "available", lambda: False)
    monkeypatch.setattr(vision_llm, "describe_image", lambda b: pytest.fail("must not be called"))

    assert vision_model.analyze_image(b"x")["style"] is None


def test_llm_answers_are_validated_against_the_project_vocabulary():
    from app.ml import vision_llm

    cleaned = vision_llm._validated({
        "category": "haut", "colors": ["noir", "turquoise", "blanc", "rouge", "bleu"], "pattern": "pois",
        "style": "Streetwear", "season": "ete", "multiple_items": 1, "confidence": 7,
    })

    assert cleaned["colors"] == ["noir", "blanc", "rouge"]  # unknown dropped, capped at 3
    assert cleaned["pattern"] is None and cleaned["style"] is None  # out-of-vocabulary -> None
    assert cleaned["season"] == "ete" and cleaned["multiple_items"] is True
    assert cleaned["confidence"] == 1.0
    assert vision_llm._validated({"category": "chapeau"}) is None  # nothing else usable -> nothing kept


def test_a_multiple_items_category_keeps_the_rest_of_the_answer():
    from app.ml import vision_llm

    kept = vision_llm._validated({"category": "multiple_items", "colors": ["bleu"], "style": "Sports", "season": "ete"})

    assert kept["category"] is None and kept["multiple_items"] is True
    assert kept["style"] == "Sports" and kept["colors"] == ["bleu"] and kept["season"] == "ete"


def test_llm_failure_returns_none_instead_of_raising(monkeypatch):
    from app.ml import vision_llm

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("VISION_LLM_ENABLED", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(vision_llm.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("quota")))
    from PIL import Image
    import io
    buffer = io.BytesIO(); Image.new("RGB", (40, 40), "white").save(buffer, format="JPEG")

    assert vision_llm.describe_image(buffer.getvalue()) is None


# ---------------------------------------------------------------- prompt versions (CRISPE)
FROZEN_PROMPT_HASHES = {  # sha256[:16] of each published prompt — see ml/reports/vision_prompt_versions.md
    "v1": "f2f587b49123ec4c", "v2": "1d3183f371acd0a5", "v3": "f66d2a8e6e3c1e0d",
    "v4": "b0894b5d25029a50", "v5": "a80994a8c85d4615",
}


def test_published_prompt_versions_are_frozen():
    import hashlib

    from app.ml import vision_llm

    current = {k: hashlib.sha256(t.encode()).hexdigest()[:16] for k, t in vision_llm.PROMPTS.items() if k in FROZEN_PROMPT_HASHES}
    assert current == FROZEN_PROMPT_HASHES, "A measured prompt version was edited: add a new version (v6...) instead."


def test_every_prompt_version_follows_the_crispe_sections():
    from app.ml import vision_llm

    for name, prompt in vision_llm.PROMPTS.items():
        for section in ("# Capacity and role", "# Insight", "# Statement", "# Personality", "# Experiment"):
            assert section in prompt, f"{name} is missing {section}"
        assert "hors_perimetre" in prompt and "JSON" in prompt


def _fake_openai(monkeypatch, sent):
    from app.core.config import get_settings
    from app.ml import vision_llm

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("VISION_LLM_ENABLED", "true")
    get_settings.cache_clear()

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": '{"category": "haut", "colors": ["noir"], "style": "Casual"}'}}]}

    monkeypatch.setattr(vision_llm.httpx, "post", lambda url, **kw: sent.append(kw["json"]) or _Resp())
    from PIL import Image
    import io

    buffer = io.BytesIO(); Image.new("RGB", (40, 40), "white").save(buffer, format="JPEG")
    return vision_llm, buffer.getvalue()


def test_the_requested_prompt_version_is_the_one_sent(monkeypatch):
    sent = []
    vision_llm, image = _fake_openai(monkeypatch, sent)

    vision_llm.describe_image(image, version="v3")
    monkeypatch.setenv("VISION_LLM_PROMPT_VERSION", "v2")
    from app.core.config import get_settings

    get_settings.cache_clear()
    vision_llm.describe_image(image)  # no explicit version -> the configured one

    assert sent[0]["messages"][0]["content"] == vision_llm.PROMPTS["v3"]
    assert sent[1]["messages"][0]["content"] == vision_llm.PROMPTS["v2"]
    assert sent[0]["temperature"] == 0 and sent[0]["response_format"] == {"type": "json_object"}


def test_an_unknown_version_falls_back_to_the_default(monkeypatch):
    sent = []
    vision_llm, image = _fake_openai(monkeypatch, sent)

    assert vision_llm.describe_image(image, version="v99")["category"] == "haut"
    assert sent[0]["messages"][0]["content"] == vision_llm.PROMPTS[vision_llm.DEFAULT_VERSION]


def test_a_transient_openai_error_is_retried_once(monkeypatch):
    from app.core.config import get_settings
    from app.ml import vision_llm

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("VISION_LLM_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr("time.sleep", lambda s: None)
    codes = iter([429, 200])

    class _Resp:
        def __init__(self, code):
            self.status_code = code

        def raise_for_status(self):
            assert self.status_code == 200

        def json(self):
            return {"choices": [{"message": {"content": '{"category": "sac", "colors": ["rouge"]}'}}]}

    monkeypatch.setattr(vision_llm.httpx, "post", lambda url, **kw: _Resp(next(codes)))
    from PIL import Image
    import io

    buffer = io.BytesIO(); Image.new("RGB", (40, 40), "white").save(buffer, format="JPEG")

    assert vision_llm.describe_image(buffer.getvalue())["category"] == "sac"
