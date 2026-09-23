from typing import Any

from app.agents.base import BaseAgent


class VisionAgent(BaseAgent):
    """Analyzes clothing images: category, color, style, pattern, visual embedding.

    Backed by a CNN / CLIP model (see architecture diagram, docs/).
    """

    name = "vision_agent"

    def run(self, *, image_url: str) -> dict[str, Any]:
        # TODO: run CLIP/CNN inference and return structured attributes + embedding
        raise NotImplementedError
