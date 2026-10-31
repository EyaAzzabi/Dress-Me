import uuid

from app.agents.style_profile_agent import StyleProfileAgent

USER_ID = uuid.uuid4()


class _FakeItem:
    def __init__(self, category, colors, style):
        self.category = category
        self.colors = colors
        self.style = style


class _FakeQuery:
    def __init__(self, items):
        self._items = items

    def filter(self, *a, **k):
        return self

    def all(self):
        return self._items


class _FakeDB:
    def __init__(self, items):
        self._items = items

    def query(self, *a, **k):
        return _FakeQuery(self._items)


def test_empty_wardrobe_returns_zeroed_profile_without_calling_llm(monkeypatch):
    called = False
    monkeypatch.setattr(
        "app.agents.style_profile_agent.LLMAgent.run",
        lambda self, **k: (_ for _ in ()).throw(AssertionError("LLM should not be called")),
    )

    agent = StyleProfileAgent(_FakeDB([]))
    result = agent.run(user_id=USER_ID)

    assert result == {
        "wardrobe_size": 0,
        "category_counts": {},
        "favorite_colors": [],
        "favorite_styles": [],
        "narrative": None,
    }


def test_aggregates_real_counts_from_the_wardrobe(monkeypatch):
    items = [
        _FakeItem("haut", ["noir"], "Casual"),
        _FakeItem("haut", ["noir"], "Casual"),
        _FakeItem("bas", ["bleu"], "Formal"),
    ]
    monkeypatch.setattr(
        "app.agents.style_profile_agent.LLMAgent.run", lambda self, **k: {"explanation": None}
    )

    agent = StyleProfileAgent(_FakeDB(items))
    result = agent.run(user_id=USER_ID)

    assert result["wardrobe_size"] == 3
    assert result["category_counts"] == {"haut": 2, "bas": 1}
    assert result["favorite_colors"][0] == "noir"
    assert result["favorite_styles"][0] == "Casual"
    assert result["narrative"] is None


def test_narrative_is_populated_from_llm_when_configured(monkeypatch):
    items = [_FakeItem("haut", ["noir"], "Casual")]
    monkeypatch.setattr(
        "app.agents.style_profile_agent.LLMAgent.run",
        lambda self, **k: {"explanation": "A casual, understated wardrobe."},
    )

    agent = StyleProfileAgent(_FakeDB(items))
    result = agent.run(user_id=USER_ID)

    assert result["narrative"] == "A casual, understated wardrobe."
