"""LLM-supervised LangGraph workflows for DressMe's multi-agent use cases.

Each specialist remains responsible for its real work (database queries, vision,
scoring, and persistence). The model chooses and sequences the specialist tools.
"""

import json
import uuid
from datetime import date, timedelta
from typing import Annotated, Any, TypedDict

from app.agents.llm_agent import LLMAgent
from app.agents.workflow_service import AgentWorkflowService, WardrobeItemRejected
from app.db import vector_store
from app.ml import clothing_gate
from app.models.packing_list import PackingList
from app.models.scheduled_outfit import ScheduledOutfit
from app.services.seasons import trip_season
from langgraph.graph.message import add_messages


class WorkflowState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    data: dict[str, Any]
    tool_steps: int


class LangGraphWorkflows:
    """Execute multi-agent workflows with a tool-calling LLM supervisor."""

    def __init__(self, workflow_service: AgentWorkflowService):
        self.workflow_service = workflow_service

    def plan_trip(
        self,
        *,
        user_id: uuid.UUID,
        destination: str,
        duration_days: int,
        trip_type: str,
        start_date: date | None,
    ) -> PackingList:
        from langchain.tools import ToolRuntime, tool

        def update(runtime: ToolRuntime, message: str, **values: Any):
            return self._tool_update(runtime, message, **values)

        @tool
        def resolve_trip_context(runtime: ToolRuntime):
            """Check destination weather, determine the trip season, and find calendar outfits already planned for the trip dates."""
            if runtime.state["data"].get("trip_context") is not None:
                return update(runtime, "Trip context is already resolved.")
            request = runtime.state["data"]["request"]
            temperature = None
            weather = self.workflow_service.context_agent.weather_service.get_current_weather(
                request["destination"]
            )
            if weather is not None:
                temperature = weather["main"]["temp"]
            season = trip_season(request["start_date"], temperature)

            required: set[uuid.UUID] = set()
            if request["start_date"] is not None:
                end_date = request["start_date"] + timedelta(days=request["duration_days"] - 1)
                planned = (
                    self.workflow_service.db.query(ScheduledOutfit)
                    .filter(
                        ScheduledOutfit.owner_id == user_id,
                        ScheduledOutfit.date >= request["start_date"],
                        ScheduledOutfit.date <= end_date,
                    )
                    .all()
                )
                required = {item_id for outfit in planned for item_id in outfit.item_ids}

            context = {"season": season, "required_item_ids": required}
            return update(
                runtime,
                f"Trip context resolved: season={season}, {len(required)} calendar items must be packed.",
                trip_context=context,
            )

        @tool
        def load_wardrobe(runtime: ToolRuntime):
            """Load the authenticated user's real wardrobe for the packing planner."""
            if runtime.state["data"].get("wardrobe_items") is not None:
                return update(runtime, "Wardrobe is already loaded.")
            items = self.workflow_service.metadata_agent.run(user_id=user_id)["items"]
            return update(runtime, f"Loaded {len(items)} wardrobe items.", wardrobe_items=items)

        @tool
        def load_wear_history(runtime: ToolRuntime):
            """Load the authenticated user's real wear history to avoid overusing the same pieces."""
            if runtime.state["data"].get("usage") is not None:
                return update(runtime, "Wear history is already loaded.")
            usage = self.workflow_service.metadata_agent.usage_history(user_id=user_id)
            return update(runtime, f"Loaded wear history for {len(usage)} items.", usage=usage)

        @tool
        def select_packing_items(runtime: ToolRuntime):
            """Choose real wardrobe items using the trip details, season, calendar commitments, and wear history."""
            state = runtime.state["data"]
            missing = [
                key for key in ("trip_context", "wardrobe_items", "usage")
                if state.get(key) is None
            ]
            if missing:
                return update(runtime, f"Load these before planning: {', '.join(missing)}.")
            if state.get("generated") is not None:
                return update(runtime, "Packing items are already selected.")

            request = state["request"]
            generated = self.workflow_service.packing_agent.run(
                wardrobe_items=state["wardrobe_items"],
                duration_days=request["duration_days"],
                trip_type=request["trip_type"],
                season=state["trip_context"]["season"],
                usage=state["usage"],
                required_item_ids=state["trip_context"]["required_item_ids"],
            )
            return update(
                runtime,
                f"Selected {len(generated['item_ids'])} real wardrobe items for the trip.",
                generated=generated,
            )

        @tool
        def save_packing_list(runtime: ToolRuntime):
            """Save the completed packing list and finish the request."""
            state = runtime.state["data"]
            if state.get("generated") is None or state.get("trip_context") is None:
                return update(runtime, "Resolve trip context and select packing items before saving.")
            if state.get("result") is not None:
                return update(runtime, "Packing list is already saved.")
            request = state["request"]
            packing_list = PackingList(
                owner_id=user_id,
                destination=request["destination"],
                duration_days=request["duration_days"],
                trip_type=request["trip_type"],
                start_date=request["start_date"],
                season=state["trip_context"]["season"],
                item_ids=state["generated"]["item_ids"],
                checked_item_ids=[],
            )
            self.workflow_service.db.add(packing_list)
            self.workflow_service.db.commit()
            self.workflow_service.db.refresh(packing_list)
            return update(runtime, "Packing list saved.", result=packing_list)

        tools = [resolve_trip_context, load_wardrobe, load_wear_history, select_packing_items, save_packing_list]
        result = self._run(
            tools=tools,
            initial_data={
                "request": {
                    "destination": destination,
                    "duration_days": duration_days,
                    "trip_type": trip_type,
                    "start_date": start_date,
                }
            },
            system_prompt=(
                "You supervise DressMe's trip-packing workflow. Use the tools to resolve the trip context, "
                "load the real wardrobe and wear history, select appropriate pieces, and save the list. "
                "Call one tool at a time and follow those dependencies. Never invent wardrobe items or "
                "claim success before the save tool confirms it."
            ),
            user_prompt=(
                "Prepare and save a packing list for this trip: "
                + json.dumps(
                    {"destination": destination, "duration_days": duration_days, "trip_type": trip_type,
                     "start_date": start_date.isoformat() if start_date else None},
                    ensure_ascii=False,
                )
            ),
            result_key="result",
            failure_message="The LangGraph supervisor stopped before saving the packing list.",
        )
        return result

    def evaluate_purchase(
        self,
        *,
        user_id: uuid.UUID,
        image_url: str,
        price: float | None,
        category: str | None,
    ) -> dict[str, Any]:
        from langchain.tools import ToolRuntime, tool

        def update(runtime: ToolRuntime, message: str, **values: Any):
            return self._tool_update(runtime, message, **values)

        @tool
        def analyze_candidate(runtime: ToolRuntime):
            """Use the vision specialist to classify the candidate garment and inspect its attributes."""
            state = runtime.state["data"]
            if state.get("attributes") is not None:
                return update(runtime, "Candidate image is already analyzed.")
            attributes = self.workflow_service.vision_agent.run(
                image_url=state["request"]["image_url"]
            )
            if not clothing_gate.is_clothing(attributes["embedding"]):
                attributes["category"] = "hors_perimetre"
            elif state["request"]["category"] and attributes["category"] != "hors_perimetre":
                attributes["category"] = state["request"]["category"]
            summary = {"category": attributes["category"], "colors": attributes.get("colors", [])[:3]}
            return update(
                runtime,
                f"Candidate analyzed: {json.dumps(summary, ensure_ascii=False)}.",
                attributes=attributes,
            )

        @tool
        def load_wardrobe_and_embeddings(runtime: ToolRuntime):
            """Load the authenticated user's wardrobe and its visual embeddings for comparison."""
            state = runtime.state["data"]
            if state.get("wardrobe") is not None:
                return update(runtime, "Wardrobe and embeddings are already loaded.")
            wardrobe = self.workflow_service.metadata_agent.run(user_id=user_id)
            embeddings = vector_store.fetch_embeddings([item.id for item in wardrobe["items"]])
            return update(
                runtime,
                f"Loaded {len(wardrobe['items'])} wardrobe items and their available embeddings.",
                wardrobe=wardrobe,
                embeddings=embeddings,
            )

        @tool
        def evaluate_candidate(runtime: ToolRuntime):
            """Score the candidate against real wardrobe items, visual matches, and the optional price."""
            state = runtime.state["data"]
            missing = [key for key in ("attributes", "wardrobe", "embeddings") if state.get(key) is None]
            if missing:
                return update(runtime, f"Load these before evaluation: {', '.join(missing)}.")
            if state.get("result") is not None:
                return update(runtime, "Candidate is already evaluated.")
            result = self.workflow_service.purchase_agent.run(
                attributes=state["attributes"],
                wardrobe_items=state["wardrobe"]["items"],
                embeddings=state["embeddings"],
                price=state["request"]["price"],
            )
            if result["item"]["category"] != "hors_perimetre":
                facts = {
                    key: result.get(key)
                    for key in (
                        "verdict",
                        "score",
                        "explanation",
                        "item",
                        "factors",
                        "outfits_unlocked",
                        "price_insight",
                    )
                }
                # Keep images, vector data, and wardrobe identifiers out of the prompt.
                facts["duplicates"] = [
                    {"category": duplicate.get("category"), "similarity": duplicate["similarity"]}
                    for duplicate in result.get("duplicates", [])
                ]
                facts["price"] = state["request"]["price"]
                facts["has_wardrobe_evidence"] = any(
                    str(item.id) in state["embeddings"]
                    for item in state["wardrobe"]["items"]
                )
                explanation = LLMAgent().run(
                    task="purchase",
                    context=facts,
                    cache_scope=str(user_id),
                    instruction="Explique le verdict fixé ; utiliser l'existant avant d'acheter.",
                )["explanation"]
                if explanation:
                    result = {**result, "explanation": explanation}
            return update(
                runtime,
                f"Purchase evaluation completed: verdict={result['verdict']}, score={result['score']}.",
                result=result,
            )

        tools = [analyze_candidate, load_wardrobe_and_embeddings, evaluate_candidate]
        return self._run(
            tools=tools,
            initial_data={"request": {"image_url": image_url, "price": price, "category": category}},
            system_prompt=(
                "You supervise DressMe's purchase evaluation workflow. Analyze the candidate with the vision "
                "specialist, load the user's real wardrobe and embeddings, then ask the purchase specialist "
                "to calculate the result. Call one tool at a time. Never invent attributes, prices, matches, "
                "or scores. Stop after evaluation is complete."
            ),
            user_prompt="Evaluate this clothing purchase using the supplied image and optional price.",
            result_key="result",
            failure_message="The LangGraph supervisor stopped before evaluating the purchase.",
        )

    def add_wardrobe_item(
        self,
        *,
        user_id: uuid.UUID,
        image_url: str,
        season: str | None,
        category: str | None,
    ):
        from langchain.tools import ToolRuntime, tool

        def update(runtime: ToolRuntime, message: str, **values: Any):
            return self._tool_update(runtime, message, **values)

        @tool
        def analyze_garment(runtime: ToolRuntime):
            """Analyze the uploaded image with the vision specialist and check whether it is a usable clothing item."""
            state = runtime.state["data"]
            if state.get("attributes") is not None or state.get("rejection") is not None:
                return update(runtime, "Garment image has already been checked.")
            attributes = self.workflow_service.wardrobe_ingestion_agent.run(
                image_url=state["request"]["image_url"], user_id=user_id
            )
            try:
                self.workflow_service._validate_wardrobe_attributes(attributes, state["request"]["category"])
            except WardrobeItemRejected as exc:
                return update(
                    runtime,
                    "Image rejected by wardrobe validation.",
                    rejection=exc.detail,
                )
            return update(runtime, "Garment image analyzed and accepted.", attributes=attributes)

        @tool
        def save_wardrobe_item(runtime: ToolRuntime):
            """Persist the analyzed clothing item and its metadata, or return the validation error."""
            state = runtime.state["data"]
            if state.get("result") is not None:
                return update(runtime, "Wardrobe item processing is already complete.")
            if state.get("rejection") is not None:
                return update(runtime, "Wardrobe item was not saved because validation failed.", result={"rejection": state["rejection"]})
            if state.get("attributes") is None:
                return update(runtime, "Analyze the garment image before saving it.")
            request = state["request"]
            item = self.workflow_service.metadata_agent.add_item(
                user_id=user_id,
                image_url=request["image_url"],
                attributes=state["attributes"],
                season=request["season"],
                category=request["category"],
            )
            return update(runtime, "Wardrobe item saved.", result=item)

        return self._run(
            tools=[analyze_garment, save_wardrobe_item],
            initial_data={"request": {"image_url": image_url, "season": season, "category": category}},
            system_prompt=(
                "You supervise adding one item to DressMe's wardrobe using the available tools. You do not receive "
                "the image itself, so you cannot judge, describe, accept, or reject it in text. Your first action "
                "must be a call to analyze_garment. Then call save_wardrobe_item; that tool enforces validation "
                "and returns a rejection when appropriate. Never answer the user directly or invent attributes."
            ),
            user_prompt=(
                "Process this wardrobe image now. Its contents are only available to the analyze_garment tool; "
                "call that tool first and then call save_wardrobe_item."
            ),
            result_key="result",
            failure_message="The LangGraph supervisor stopped before processing the wardrobe item.",
        )

    @staticmethod
    def _tool_update(runtime, message: str, **values: Any):
        from langchain.messages import ToolMessage
        from langgraph.types import Command

        data = dict(runtime.state.get("data") or {})
        data.update(values)
        return Command(
            update={
                "data": data,
                "tool_steps": runtime.state.get("tool_steps", 0) + 1,
                "messages": [ToolMessage(content=message, tool_call_id=runtime.tool_call_id)],
            }
        )

    @staticmethod
    def _run(
        *,
        tools: list[Any],
        initial_data: dict[str, Any],
        system_prompt: str,
        user_prompt: str,
        result_key: str,
        failure_message: str,
    ):
        from langchain.messages import HumanMessage, SystemMessage
        from langgraph.graph import END, START, StateGraph
        from langgraph.prebuilt import ToolNode

        # These workflows cannot finish without the specialist tools running. Keep
        # the LLM in charge of choosing the next tool, but don't let an ordinary
        # text-only response end the graph before it has processed the request.
        model = LLMAgent().as_chat_model().bind_tools(
            tools, parallel_tool_calls=False, tool_choice="required"
        )

        def supervisor(state: WorkflowState) -> dict[str, Any]:
            return {"messages": [model.invoke(state["messages"])]}

        def after_supervisor(state: WorkflowState) -> str:
            last = state["messages"][-1]
            return "tools" if getattr(last, "tool_calls", None) else END

        def after_tools(state: WorkflowState) -> str:
            data = state.get("data") or {}
            if data.get(result_key) is not None or state.get("tool_steps", 0) >= 12:
                return END
            return "supervisor"

        builder = StateGraph(WorkflowState)
        builder.add_node("supervisor", supervisor)
        builder.add_node("tools", ToolNode(tools))
        builder.add_edge(START, "supervisor")
        builder.add_conditional_edges("supervisor", after_supervisor, {"tools": "tools", END: END})
        builder.add_conditional_edges("tools", after_tools, {"supervisor": "supervisor", END: END})
        final_state = builder.compile().invoke(
            {
                "messages": [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
                "data": initial_data,
                "tool_steps": 0,
            },
            config={"recursion_limit": 30},
        )
        data = final_state.get("data") or {}
        result = data.get(result_key)
        if result is None:
            raise RuntimeError(failure_message)
        if isinstance(result, dict) and "rejection" in result:
            raise WardrobeItemRejected(result["rejection"])
        return result
