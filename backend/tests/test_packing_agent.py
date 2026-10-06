import uuid

from app.agents.packing_agent import PackingAgent


class _FakeItem:
    def __init__(self, category: str, style: str | None = None):
        self.id = uuid.uuid4()
        self.category = category
        self.style = style


def test_targets_scale_with_trip_duration():
    items = [_FakeItem("haut", "Casual") for _ in range(10)] + [_FakeItem("bas", "Casual") for _ in range(10)]

    result = PackingAgent().run(wardrobe_items=items, duration_days=4, trip_type="tourisme")

    hauts = [i for i in items if i.category == "haut" and i.id in result["item_ids"]]
    bas = [i for i in items if i.category == "bas" and i.id in result["item_ids"]]
    assert len(hauts) == 4  # one per day
    assert len(bas) == 2  # ceil(4/2)


def test_plage_trip_excludes_veste():
    items = [_FakeItem("veste", "Casual"), _FakeItem("haut", "Casual"), _FakeItem("bas", "Casual")]

    result = PackingAgent().run(wardrobe_items=items, duration_days=2, trip_type="plage")

    veste = next(i for i in items if i.category == "veste")
    assert veste.id not in result["item_ids"]


def test_preferred_style_is_picked_over_others_when_both_available():
    formal = _FakeItem("haut", "Formal")
    casual = _FakeItem("haut", "Casual")

    result = PackingAgent().run(wardrobe_items=[formal, casual], duration_days=1, trip_type="business")

    assert formal.id in result["item_ids"]
    assert casual.id not in result["item_ids"]


def test_falls_back_to_non_preferred_style_when_not_enough_matches():
    only_casual = [_FakeItem("haut", "Casual") for _ in range(2)]

    result = PackingAgent().run(wardrobe_items=only_casual, duration_days=3, trip_type="business")

    # business prefers Formal/Smart Casual, but none exist — still returns what's there
    assert len(result["item_ids"]) == 2


def test_missing_category_simply_yields_nothing_for_that_slot():
    items = [_FakeItem("haut", "Casual")]

    result = PackingAgent().run(wardrobe_items=items, duration_days=3, trip_type="tourisme")

    assert result["item_ids"] == [items[0].id]
