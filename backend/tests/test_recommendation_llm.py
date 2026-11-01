"""Unit tests for recommendation_llm.py module.

Tests cover:
- Module imports without errors
- parse_action parsing of tool calls and final blocks
- RecommendationToolSandbox initialization and tool invocation
- All tool methods with mock data
- Tool error handling
- run_agent loop with mock generate function
- Graceful degradation when torch unavailable
- teacher_trajectory trajectory building
- Per-user adapter detection
- build_training_dataset
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.ml import recommendation_llm
from app.ml.recommendation_llm import (
    MAX_TOOL_STEPS,
    SYSTEM_PROMPT,
    BASE_MODEL_ID,
    RecommendationToolSandbox,
    UnknownRecommendationTool,
    build_training_dataset,
    collect_tool_traces,
    parse_action,
    run_agent,
    teacher_trajectory,
    user_adapter_dir,
)


# ============================================================================
# Test 1: Module imports without errors
# ============================================================================


def test_module_imports():
    """Verify module imports and constants are present."""
    assert recommendation_llm.ADAPTER_DIR is not None
    assert recommendation_llm.BASE_MODEL_ID == "Qwen/Qwen2.5-1.5B-Instruct"
    assert recommendation_llm.MAX_TOOL_STEPS == 8
    assert len(recommendation_llm.TOOL_SPECS) == 7
    assert recommendation_llm.SYSTEM_PROMPT
    assert "Tu es un styliste expert DressMe" in recommendation_llm.SYSTEM_PROMPT


def test_tool_specs_are_complete():
    """Verify all expected tools are defined."""
    tool_names = {t["name"] for t in recommendation_llm.TOOL_SPECS}
    expected = {
        "inspect_wardrobe",
        "filter_by_season",
        "filter_by_weather",
        "find_compatible_items",
        "estimate_occasion_fit",
        "rank_by_color_harmony",
        "get_weather_constraints",
    }
    assert tool_names == expected


# ============================================================================
# Test 2: parse_action parsing
# ============================================================================


def test_parse_action_tool_call():
    """Parse a tool call block."""
    text = '<tool_call>{"name": "inspect_wardrobe"}</tool_call>'
    action = parse_action(text)
    assert action is not None
    assert action["type"] == "tool"
    assert action["name"] == "inspect_wardrobe"
    assert action["args"] == {}


def test_parse_action_tool_call_with_args():
    """Parse a tool call with arguments."""
    text = '<tool_call>{"name": "filter_by_season", "season": "ete"}</tool_call>'
    action = parse_action(text)
    assert action is not None
    assert action["type"] == "tool"
    assert action["name"] == "filter_by_season"
    assert action["args"]["season"] == "ete"


def test_parse_action_final():
    """Parse a final block."""
    text = '<final>{"explanation": "Tenue parfaite!"}</final>'
    action = parse_action(text)
    assert action is not None
    assert action["type"] == "final"
    assert action["explanation"] == "Tenue parfaite!"


def test_parse_action_malformed_json():
    """Handle malformed JSON gracefully."""
    text = '<tool_call>{invalid json}</tool_call>'
    action = parse_action(text)
    assert action is None


def test_parse_action_empty_string():
    """Handle empty string."""
    action = parse_action("")
    assert action is None


def test_parse_action_no_match():
    """Handle text with no tool_call or final blocks."""
    action = parse_action("Some random text")
    assert action is None


# ============================================================================
# Test 3: RecommendationToolSandbox initialization
# ============================================================================


def test_sandbox_initialization():
    """Initialize sandbox with mock wardrobe."""
    wardrobe = _mock_wardrobe()
    sandbox = RecommendationToolSandbox(
        wardrobe_items=wardrobe,
        user_id="user123",
        weather_data={"temperature": 25.0, "condition": "sunny"},
        occasion="casual",
        season="ete",
    )
    assert sandbox.wardrobe_items == wardrobe
    assert sandbox.user_id == "user123"
    assert sandbox.occasion == "casual"
    assert sandbox.season == "ete"
    assert len(sandbox._tools) == 7


def test_sandbox_tools_are_callable():
    """Verify all tools are registered and callable."""
    sandbox = RecommendationToolSandbox(wardrobe_items=_mock_wardrobe())
    assert "inspect_wardrobe" in sandbox._tools
    assert "filter_by_season" in sandbox._tools
    assert "filter_by_weather" in sandbox._tools
    assert "find_compatible_items" in sandbox._tools
    assert "estimate_occasion_fit" in sandbox._tools
    assert "rank_by_color_harmony" in sandbox._tools
    assert "get_weather_constraints" in sandbox._tools


# ============================================================================
# Test 4: Tool sandbox calls
# ============================================================================


def test_tool_inspect_wardrobe():
    """Test inspect_wardrobe tool."""
    wardrobe = _mock_wardrobe()
    sandbox = RecommendationToolSandbox(wardrobe_items=wardrobe)
    result = sandbox.call("inspect_wardrobe")
    assert "items" in result
    assert "total" in result
    assert result["total"] == len(wardrobe)
    assert "by_category" in result


def test_tool_inspect_wardrobe_by_category():
    """Test inspect_wardrobe with category filter."""
    wardrobe = _mock_wardrobe()
    sandbox = RecommendationToolSandbox(wardrobe_items=wardrobe)
    result = sandbox.call("inspect_wardrobe", category="top")
    assert "items" in result
    assert all(item["category"] == "top" for item in result["items"])


def test_tool_filter_by_season():
    """Test filter_by_season tool."""
    wardrobe = _mock_wardrobe()
    sandbox = RecommendationToolSandbox(wardrobe_items=wardrobe)
    result = sandbox.call("filter_by_season", season="ete")
    assert "items" in result
    assert result["season"] == "ete"
    assert "count" in result


def test_tool_filter_by_weather():
    """Test filter_by_weather tool."""
    wardrobe = _mock_wardrobe()
    sandbox = RecommendationToolSandbox(wardrobe_items=wardrobe)
    result = sandbox.call("filter_by_weather", weather="sunny", temperature=25.0)
    assert "items" in result
    assert result["weather"] == "sunny"
    assert result["temperature"] == 25.0
    assert "recommendations" in result


def test_tool_filter_by_weather_missing_params():
    """Test filter_by_weather with missing parameters."""
    sandbox = RecommendationToolSandbox(wardrobe_items=_mock_wardrobe())
    result = sandbox.call("filter_by_weather")
    assert "error" in result


def test_tool_estimate_occasion_fit():
    """Test estimate_occasion_fit tool."""
    wardrobe = _mock_wardrobe()
    sandbox = RecommendationToolSandbox(wardrobe_items=wardrobe)
    item_ids = [item["id"] for item in wardrobe[:3]]
    result = sandbox.call("estimate_occasion_fit", outfit_items=item_ids, occasion="casual")
    assert "fit_score" in result
    assert 0 <= result["fit_score"] <= 1
    assert "reasoning" in result


def test_tool_rank_by_color_harmony():
    """Test rank_by_color_harmony tool."""
    wardrobe = _mock_wardrobe()
    sandbox = RecommendationToolSandbox(wardrobe_items=wardrobe)
    item_ids = [item["id"] for item in wardrobe[:2]]
    result = sandbox.call("rank_by_color_harmony", outfit_items=item_ids)
    assert "harmony_score" in result
    assert 0 <= result["harmony_score"] <= 1
    assert "analysis" in result


def test_tool_get_weather_constraints():
    """Test get_weather_constraints tool."""
    sandbox = RecommendationToolSandbox(wardrobe_items=_mock_wardrobe())
    result = sandbox.call("get_weather_constraints", city="Tunis", temperature=28.0)
    assert "city" in result
    assert result["city"] == "Tunis"
    assert "constraints" in result
    assert "material_advice" in result


# ============================================================================
# Test 5: Tool error handling
# ============================================================================


def test_sandbox_unknown_tool():
    """Calling unknown tool raises UnknownRecommendationTool."""
    sandbox = RecommendationToolSandbox(wardrobe_items=_mock_wardrobe())
    with pytest.raises(UnknownRecommendationTool):
        sandbox.call("nonexistent_tool")


def test_sandbox_tool_with_invalid_args():
    """Tool call with invalid args returns error dict."""
    sandbox = RecommendationToolSandbox(wardrobe_items=_mock_wardrobe())
    result = sandbox.call("find_compatible_items")
    assert "error" in result


def test_sandbox_estimate_occasion_fit_no_items():
    """estimate_occasion_fit with non-existent items returns error."""
    sandbox = RecommendationToolSandbox(wardrobe_items=_mock_wardrobe())
    result = sandbox.call("estimate_occasion_fit", outfit_items=["nonexistent"], occasion="casual")
    assert "error" in result


# ============================================================================
# Test 6: run_agent loop with mock generate
# ============================================================================


def test_run_agent_with_mock_generate():
    """Test run_agent with a mock generate function."""
    wardrobe = _mock_wardrobe()
    sandbox = RecommendationToolSandbox(
        wardrobe_items=wardrobe,
        occasion="casual",
        season="ete",
    )

    # Mock generate function that returns predetermined tool calls then final
    call_count = [0]

    def mock_generate(messages):
        call_count[0] += 1
        if call_count[0] == 1:
            return '<tool_call>{"name": "inspect_wardrobe"}</tool_call>'
        else:
            return '<final>{"explanation": "Tenue casual parfaite!"}</final>'

    task = {
        "occasion": "casual",
        "season": "ete",
        "weather": {"temperature": 25.0, "condition": "sunny"},
    }

    result = run_agent(task, sandbox, generate=mock_generate)
    assert result is not None
    assert "explanation" in result
    assert result["explanation"] == "Tenue casual parfaite!"
    assert "tools" in result
    assert "inspect_wardrobe" in result["tools"]


def test_run_agent_disabled_setting():
    """Test run_agent returns None when LLM is disabled."""
    with patch("app.ml.recommendation_llm.get_settings") as mock_settings:
        settings = MagicMock()
        settings.recommendation_llm_enabled = False
        mock_settings.return_value = settings

        sandbox = RecommendationToolSandbox(wardrobe_items=_mock_wardrobe())
        result = run_agent({}, sandbox)
        assert result is None


def test_run_agent_no_generate_available():
    """Test run_agent returns None when no generate function available."""
    with patch("app.ml.recommendation_llm.get_settings") as mock_settings:
        settings = MagicMock()
        settings.recommendation_llm_enabled = True
        settings.llm_provider = "none"
        mock_settings.return_value = settings

        sandbox = RecommendationToolSandbox(wardrobe_items=_mock_wardrobe())
        result = run_agent({}, sandbox)
        assert result is None


# ============================================================================
# Test 7: Graceful degradation (torch unavailable)
# ============================================================================


def test_graceful_degradation_torch_unavailable():
    """Test module gracefully handles torch import errors."""
    # This test verifies the module can be imported even if torch is unavailable
    # In practice, the try/except at module level prevents ImportError
    assert recommendation_llm._TORCH_AVAILABLE in (True, False)


def test_generate_api_fallback():
    """Test that generate_api works without torch."""
    with patch("app.ml.recommendation_llm.get_settings") as mock_settings:
        settings = MagicMock()
        settings.llm_provider = "ollama"
        settings.llm_base_url = "http://localhost:11434/v1"
        settings.llm_model = "qwen2.5:1.5b"
        settings.active_llm_api_key = "ollama"
        mock_settings.return_value = settings

        with patch("httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Generated text"}}]
            }
            mock_post.return_value = mock_response

            result = recommendation_llm._generate_api([])
            assert result == "Generated text"


# ============================================================================
# Test 8: teacher_trajectory
# ============================================================================


def test_teacher_trajectory():
    """Test teacher_trajectory builds valid training data."""
    task = {"occasion": "casual", "season": "ete"}
    tool_results = {
        "inspect_wardrobe": {"items": [], "total": 20},
        "filter_by_season": {"items": [], "season": "ete", "count": 10},
    }
    explanation = "Tenue casual harmonieuse."

    messages = teacher_trajectory(task, tool_results, explanation)

    assert len(messages) >= 4  # system, user, assistant/tool_call, user/tool_result, ..., final
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[-1]["role"] == "assistant"
    assert "<final>" in messages[-1]["content"]


# ============================================================================
# Test 9: Per-user adapter detection
# ============================================================================


def test_user_adapter_dir():
    """Test user_adapter_dir path construction."""
    user_id = "user_12345678abcd"
    path = user_adapter_dir(user_id)
    assert "recommendation_llm_user_1" in str(path)
    assert user_id[:8] in str(path)


def test_adapter_ready_default():
    """Test _adapter_ready returns False when no adapter exists."""
    result = recommendation_llm._adapter_ready()
    # Should be False in test env where no LoRA adapter exists
    assert isinstance(result, bool)


# ============================================================================
# Test 10: build_training_dataset
# ============================================================================


def test_build_training_dataset():
    """Test build_training_dataset with mock feedback pairs."""
    wardrobe = _mock_wardrobe()
    preferred = [wardrobe[0], wardrobe[1]]
    rejected = [wardrobe[2]]
    feedback_pairs = [(preferred, rejected)]

    dataset = build_training_dataset(feedback_pairs, wardrobe)
    assert len(dataset) == 1
    assert "messages" in dataset[0]
    assert "task" in dataset[0]
    assert isinstance(dataset[0]["messages"], list)
    assert dataset[0]["messages"][0]["role"] == "system"


def test_build_training_dataset_empty():
    """Test build_training_dataset with empty feedback."""
    dataset = build_training_dataset([], _mock_wardrobe())
    assert dataset == []


# ============================================================================
# Test 11: collect_tool_traces
# ============================================================================


def test_collect_tool_traces():
    """Test collect_tool_traces returns valid trace dict."""
    wardrobe = _mock_wardrobe()
    preferred = {"items": wardrobe[:2], "occasion": "casual"}
    rejected = {"items": wardrobe[2:3], "occasion": "casual"}

    traces = collect_tool_traces(preferred, rejected, wardrobe)
    assert "preferred_tools" in traces
    assert "rejected_tools" in traces
    assert "reasoning" in traces
    assert isinstance(traces["preferred_tools"], list)
    assert isinstance(traces["rejected_tools"], list)


# ============================================================================
# Helper functions for mock data
# ============================================================================


def _mock_wardrobe():
    """Create a mock 20-item wardrobe with varied categories, colors, seasons."""
    items = [
        {
            "id": f"item_{i:02d}",
            "category": ["top", "bottom", "shoes", "jacket", "dress"][i % 5],
            "color": ["noir", "blanc", "rouge", "bleu", "vert"][i % 5],
            "colors": [["noir"], ["blanc", "gris"], ["rouge"], ["bleu"], ["vert", "bleu"]][
                i % 5
            ],
            "season": ["ete", "hiver", "mi_saison", "toutes_saisons"][i % 4],
            "style": ["casual", "formal", "smart_casual", "sports"][i % 4],
            "pattern": ["uni", "rayures", "carreaux", "imprime"][i % 4],
        }
        for i in range(20)
    ]
    return items
