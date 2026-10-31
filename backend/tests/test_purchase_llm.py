from app.ml import purchase_llm
from app.services.purchase_tools import PurchaseToolSandbox, UnknownPurchaseTool


def test_model_output_is_parsed_as_a_sandbox_tool_call():
    action = purchase_llm.parse_action('<tool_call>{"name": "inspect_wardrobe"}</tool_call>')

    assert action == {"type": "tool", "name": "inspect_wardrobe", "args": {}}


def test_model_output_is_parsed_as_a_final_answer():
    action = purchase_llm.parse_action('<final>{"explanation": "Bon achat : ce haut crée 3 tenues."}</final>')

    assert action["type"] == "final"
    assert "tenues" in action["explanation"]


def test_agent_loop_calls_sandbox_tools_then_stops(monkeypatch):
    replies = [
        '<tool_call>{"name": "inspect_wardrobe"}</tool_call>',
        '<final>{"explanation": "Rien de similaire dans ta garde-robe."}</final>',
    ]
    sandbox = PurchaseToolSandbox.__new__(PurchaseToolSandbox)
    sandbox._tools = {"inspect_wardrobe": lambda: {"wardrobe_size": 0, "duplicates": []}}
    monkeypatch.setattr("app.ml.purchase_llm.get_settings", lambda: type("S", (), {
        "purchase_llm_enabled": True, "llm_provider": "none", "llm_api_key": None,
        "llm_base_url": None, "llm_model": None,
    })())

    out = purchase_llm.run_agent(
        {"category": "haut", "price": 59, "wardrobe_size": 0},
        sandbox,
        generate=lambda messages: replies.pop(0),
    )

    assert out["tools"] == ["inspect_wardrobe"]
    assert "garde-robe" in out["text"]


def test_agent_cannot_call_a_tool_outside_the_sandbox(monkeypatch):
    sandbox = PurchaseToolSandbox.__new__(PurchaseToolSandbox)
    sandbox._tools = {"inspect_wardrobe": lambda: {}}
    monkeypatch.setattr("app.ml.purchase_llm.get_settings", lambda: type("S", (), {
        "purchase_llm_enabled": True, "llm_provider": "none",
        "llm_api_key": None, "llm_base_url": None, "llm_model": None,
    })())

    out = purchase_llm.run_agent(
        {"category": "haut"},
        sandbox,
        generate=lambda messages: '<tool_call>{"name": "os_system"}</tool_call>',
    )

    assert out is None


def test_sandbox_still_rejects_unknown_names_directly():
    try:
        PurchaseToolSandbox().call("eval")
    except UnknownPurchaseTool:
        return
    raise AssertionError("expected UnknownPurchaseTool")
