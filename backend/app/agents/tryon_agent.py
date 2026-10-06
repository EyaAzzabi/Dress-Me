import time
from typing import Any

import httpx

from app.agents.base import BaseAgent
from app.core.config import get_settings

REPLICATE_API_BASE = "https://api.replicate.com/v1"
POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 120.0


class TryOnAgent(BaseAgent):
    """Virtual try-on: composites a wardrobe item's photo onto the user's own
    reference photo via a hosted diffusion model (Replicate — no local GPU, this
    stack is CPU-only and a real try-on model needs one for practical latency).

    Deliberately stateless — returns the generated image URL to the caller on every
    call rather than persisting try-on history, a scope decision, not an oversight;
    add a TryOnResult table later if history/sharing is actually needed.
    """

    name = "tryon_agent"

    def __init__(self) -> None:
        self.settings = get_settings()

    def is_configured(self) -> bool:
        return bool(self.settings.replicate_api_token and self.settings.replicate_tryon_model_version)

    def run(self, *, person_image_url: str, garment_image_url: str, **kwargs: Any) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError(
                "Virtual try-on isn't configured (REPLICATE_API_TOKEN / "
                "REPLICATE_TRYON_MODEL_VERSION missing)."
            )

        headers = {"Authorization": f"Token {self.settings.replicate_api_token}"}
        create = httpx.post(
            f"{REPLICATE_API_BASE}/predictions",
            headers=headers,
            json={
                "version": self.settings.replicate_tryon_model_version,
                "input": {"human_img": person_image_url, "garm_img": garment_image_url},
            },
            timeout=30.0,
        )
        try:
            create.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Surfaced as-is rather than a generic 500 — callers (app/api/routes/
            # tryon.py) turn this into a clear detail message for the client. 402
            # specifically means the Replicate account has no billing/credits set up.
            raise RuntimeError(
                f"Replicate request failed ({create.status_code}): {create.text}"
            ) from exc
        prediction = create.json()

        result = self._poll_until_done(prediction["urls"]["get"], headers)
        if result["status"] != "succeeded":
            raise RuntimeError(f"Try-on generation failed: {result.get('error', 'unknown error')}")

        output = result["output"]
        image_url = output[0] if isinstance(output, list) else output
        return {"result_image_url": image_url}

    def _poll_until_done(self, prediction_url: str, headers: dict) -> dict:
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        while True:
            response = httpx.get(prediction_url, headers=headers, timeout=15.0)
            response.raise_for_status()
            result = response.json()
            if result["status"] in ("succeeded", "failed", "canceled"):
                return result
            if time.monotonic() > deadline:
                raise TimeoutError("Try-on generation timed out.")
            time.sleep(POLL_INTERVAL_SECONDS)
