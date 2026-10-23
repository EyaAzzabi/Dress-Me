"""LLM-supervised outfit recommendations implemented with LangGraph.

The model chooses which specialist tools to invoke. The existing agents continue to
own database access, image/vector lookups, outfit scoring, and persistence.
"""

import json
import uuid
from typing import Annotated, Any, TypedDict

from app.agents.llm_agent import LLMAgent
from app.agents.workflow_service import AgentWorkflowService
from app.core.config import get_settings
from app.ml import ranking_model
from app.rag import context_retrieval
from app.services import occasions
from langgraph.graph.message import add_messages


class RecommendationState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    request: dict[str, Any]
    context: dict[str, Any]
    style_profile: dict[str, Any]
    usage: dict[uuid.UUID, dict[str, Any]]
    wardrobe_items: list[Any]
    generated: dict[str, Any]
    result: dict[str, Any]
    tool_steps: int
    full_wardrobe_loaded: bool


class LangGraphRecommendation:
    """Run the recommendation workflow under an LLM tool-calling supervisor."""

    def __init__(self, workflow_service: AgentWorkflowService):
        self.workflow_service = workflow_service

    def run(
        self,
        *,
        user_id: uuid.UUID,
        occasion: str | None,
        weather: str | None,
        season: str | None,
        city: str | None,
    ) -> dict[str, Any]:
        from langchain.messages import HumanMessage, SystemMessage, ToolMessage
        from langchain.tools import ToolRuntime, tool
        from langgraph.graph import END, START, StateGraph
        from langgraph.graph.message import add_messages
        from langgraph.prebuilt import ToolNode
        from langgraph.types import Command

        request = {
            "occasion": occasion,
            "weather": weather,
            "season": season,
            "city": city,
        }

        def tool_update(runtime: ToolRuntime, message: str, **updates: Any) -> Command:
            return Command(
                update={
                    **updates,
                    "tool_steps": runtime.state.get("tool_steps", 0) + 1,
                    "messages": [ToolMessage(content=message, tool_call_id=runtime.tool_call_id)],
                }
            )

        @tool
        def resolve_context(runtime: ToolRuntime) -> Command:
            """Resolve the request's occasion, weather, city, and season context."""
            if runtime.state.get("context") is not None:
                return tool_update(runtime, "Context is already resolved.")
            values = runtime.state["request"]
            context = self.workflow_service.context_agent.run(**values)
            return tool_update(runtime, f"Context resolved: {context}.", context=context)

        @tool
        def get_style_profile(runtime: ToolRuntime) -> Command:
            """Load this authenticated user's wardrobe-derived style profile."""
            if runtime.state.get("style_profile") is not None:
                return tool_update(runtime, "Style profile is already loaded.")
            profile = self.workflow_service.style_profile_agent.run(
                user_id=user_id, include_narrative=False
            )
            summary = {
                "favorite_styles": profile.get("favorite_styles", []),
                "favorite_colors": profile.get("favorite_colors", []),
                "wardrobe_size": profile.get("wardrobe_size", 0),
            }
            return tool_update(
                runtime,
                f"Style profile loaded: {json.dumps(summary, ensure_ascii=False)}.",
                style_profile=profile,
            )

        @tool
        def get_wear_history(runtime: ToolRuntime) -> Command:
            """Load recent wear history so suggestions can avoid repeating pieces."""
            if runtime.state.get("usage") is not None:
                return tool_update(runtime, "Wear history is already loaded.")
            usage = self.workflow_service.metadata_agent.usage_history(user_id=user_id)
            return tool_update(
                runtime,
                f"Wear history loaded for {len(usage)} wardrobe items.",
                usage=usage,
            )

        @tool
        def load_wardrobe(runtime: ToolRuntime) -> Command:
            """Load wardrobe items that can be worn in the resolved season."""
            if runtime.state.get("context") is None:
                return tool_update(runtime, "Resolve context before loading seasonal wardrobe items.")
            if runtime.state.get("wardrobe_items") is not None:
                return tool_update(runtime, "Wardrobe is already loaded.")
            context = runtime.state["context"]
            items = self.workflow_service.metadata_agent.run(
                user_id=user_id, wearable_in=context.get("season")
            )["items"]
            return tool_update(runtime, f"Loaded {len(items)} wardrobe items.", wardrobe_items=items)

        @tool
        def generate_outfits(runtime: ToolRuntime) -> Command:
            """Generate and score outfits from the loaded wardrobe and profile."""
            state = runtime.state
            missing = [
                name
                for name in ("context", "style_profile", "usage", "wardrobe_items")
                if state.get(name) is None
            ]
            if missing:
                return tool_update(
                    runtime,
                    f"Cannot generate yet; load these first: {', '.join(missing)}.",
                )
            if state.get("generated") is not None:
                return tool_update(runtime, "Outfits are already generated.")

            context = state["context"]
            profile = state.get("style_profile") or {}
            usage = state.get("usage") or {}
            items = state["wardrobe_items"]
            weather_band = occasions.weather_band(context.get("temperature"))
            ctx_vec = ranking_model.context_vector(
                context.get("occasion_category"), context.get("season"), weather_band
            )
            references = None
            if get_settings().contextual_rag_enabled:
                references = context_retrieval.retrieve_references(
                    self.workflow_service.db, user_id, context, ctx_vec
                )
            generated = self.workflow_service.recommendation_agent.run(
                wardrobe_items=items,
                occasion=context.get("occasion"),
                favorite_styles=profile.get("favorite_styles", []),
                usage=usage,
                season=context.get("season"),
                temperature=context.get("temperature"),
                weather=context.get("weather"),
                occasion_category=context.get("occasion_category"),
                formality=context.get("formality"),
                references=references,
                ctx_vec=ctx_vec,
            )

            return tool_update(
                runtime,
                f"Generated {len(generated['outfits'])} outfit recommendations.",
                generated=generated,
            )

        @tool
        def load_full_wardrobe(runtime: ToolRuntime) -> Command:
            """Load every wardrobe item when the seasonal selection produced no outfits, so the supervisor can retry."""
            state = runtime.state
            generated = state.get("generated")
            context = state.get("context") or {}
            if generated is None or generated.get("outfits") or not context.get("season"):
                return tool_update(
                    runtime,
                    "The full wardrobe retry is only available after an empty seasonal result.",
                )
            if state.get("full_wardrobe_loaded"):
                return tool_update(runtime, "The full wardrobe has already been loaded.")
            items = self.workflow_service.metadata_agent.run(user_id=user_id)["items"]
            return tool_update(
                runtime,
                f"Loaded all {len(items)} wardrobe items for a retry.",
                wardrobe_items=items,
                generated=None,
                full_wardrobe_loaded=True,
            )

        @tool
        def save_recommendations(runtime: ToolRuntime) -> Command:
            """Persist generated outfits and finish the recommendation request."""
            state = runtime.state
            if state.get("generated") is None or state.get("context") is None:
                return tool_update(runtime, "Resolve context and generate outfits before saving.")
            if state.get("result") is not None:
                return tool_update(runtime, "Recommendations are already saved.")
            result = self.workflow_service._save_recommendations(
                user_id=user_id,
                context=state["context"],
                generated=state["generated"],
                wardrobe_items=state.get("wardrobe_items", []),
                style_profile=state.get("style_profile") or {},
            )
            return tool_update(
                runtime,
                f"Saved {len(result['outfits'])} recommendations.",
                result=result,
            )

        tools = [
            resolve_context,
            get_style_profile,
            get_wear_history,
            load_wardrobe,
            generate_outfits,
            load_full_wardrobe,
            save_recommendations,
        ]
        model = LLMAgent().as_chat_model().bind_tools(tools, parallel_tool_calls=False)

        system_message = SystemMessage(
            content=(
                "You supervise DressMe's outfit recommendation workflow. Use the available "
                "tools to gather real user data and finish the request. Choose the tool order "
                "while respecting dependencies: resolve context and load a wardrobe before "
                "generating outfits, then save the result. Use profile and wear history for "
                "personalization. If the seasonal selection produces no outfits, load the full "
                "wardrobe and retry. Call one tool at a time and never invent wardrobe items, "
                "scores, or user data. The tools execute database and scoring operations; your "
                "role is to choose and sequence them. Stop after recommendations are saved."
            )
        )

        def supervisor(state: RecommendationState) -> dict[str, Any]:
            return {"messages": [model.invoke(state["messages"])]}

        def after_supervisor(state: RecommendationState) -> str:
            last = state["messages"][-1]
            return "tools" if getattr(last, "tool_calls", None) else END

        def after_tools(state: RecommendationState) -> str:
            if state.get("result") is not None or state.get("tool_steps", 0) >= 12:
                return END
            return "supervisor"

        builder = StateGraph(RecommendationState)
        builder.add_node("supervisor", supervisor)
        builder.add_node("tools", ToolNode(tools))
        builder.add_edge(START, "supervisor")
        builder.add_conditional_edges("supervisor", after_supervisor, {"tools": "tools", END: END})
        builder.add_conditional_edges("tools", after_tools, {"supervisor": "supervisor", END: END})
        graph = builder.compile()

        final_state = graph.invoke(
            {
                "messages": [
                    system_message,
                    HumanMessage(
                        content=(
                            "Create outfit recommendations for this request. "
                            f"Structured request: {json.dumps(request, ensure_ascii=False)}"
                        )
                    ),
                ],
                "request": request,
                "tool_steps": 0,
            },
            config={"recursion_limit": 30},
        )
        result = final_state.get("result")
        if result is None:
            raise RuntimeError("The LangGraph supervisor stopped before saving recommendations.")
        return result
