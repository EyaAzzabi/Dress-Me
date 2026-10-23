"""Compatibility imports; multi-agent orchestration is implemented with LangGraph."""

from app.agents.workflow_service import AgentWorkflowService, WardrobeItemRejected

AgentOrchestrator = AgentWorkflowService

__all__ = ["AgentOrchestrator", "AgentWorkflowService", "WardrobeItemRejected"]
