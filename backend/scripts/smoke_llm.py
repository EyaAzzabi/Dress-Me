"""Explicit opt-in live provider check: python -m scripts.smoke_llm.

Synthetic facts only. Never prints credentials; exits nonzero on fallback so a
successful deterministic test cannot be mistaken for a successful provider call.
"""
from app.agents.llm_agent import LLMAgent


def main() -> int:
    agent = LLMAgent()
    if agent.settings.llm_provider == "none":
        print("Set LLM_PROVIDER and (for a hosted provider) LLM_API_KEY in backend/.env.")
        return 2
    result = agent.run(
        context={"wardrobe_size": 2, "category_counts": {"haut": 1, "bas": 1},
                 "favorite_colors": ["beige", "noir"], "favorite_styles": ["Casual"]},
        instruction="Décris ce profil en français.", cache_scope="synthetic-smoke-test",
    )
    if result["explanation"] is None:
        print("Provider check failed or returned an invalid plan. Check configuration, model and quota.")
        return 1
    print(result["explanation"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
