import time
from typing import Any

import httpx

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.services.storage import StorageService

REPLICATE_API_BASE = "https://api.replicate.com/v1"
POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 120.0

# What the try-on model dresses, per wardrobe category. Shoes/bags/accessories can't be
# composited onto a body photo by this kind of model, so they're left out of a render.
GARMENT_CATEGORY = {"robe": "dresses", "bas": "lower_body", "haut": "upper_body", "veste": "upper_body"}
# The Hugging Face Space (OOTDiffusion) names the same three categories differently.
HF_CATEGORY = {"upper_body": "Upper-body", "lower_body": "Lower-body", "dresses": "Dress"}
HF_TIMEOUT_SECONDS = 300.0

# Layering order: base layers first, so the jacket ends up on top of the top.
LAYER_ORDER = ["robe", "bas", "haut", "veste"]


def garments_for_outfit(items) -> list[tuple[str, str]]:
    """(image_url, model category) per wearable piece of an outfit, in layering order.
    One piece per layer — a second top would just overwrite the first."""
    chosen = {}
    for item in items:
        if item.category in GARMENT_CATEGORY and item.category not in chosen:
            chosen[item.category] = item
    return [(chosen[c].image_url, GARMENT_CATEGORY[c]) for c in LAYER_ORDER if c in chosen]


class TryOnAgent(BaseAgent):
    """Virtual try-on: composites a wardrobe item's photo onto the user's own
    reference photo via a hosted diffusion model — no local GPU, this stack is CPU-only
    and a real try-on model needs one for practical latency. Two providers: Replicate
    (paid, needs an API token) or a public Hugging Face Space (free; see
    Settings.tryon_provider). The result is always a URL; the Hugging Face path also
    saves the picture to our own storage, since the Space only hands back a temp file.

    Deliberately stateless — returns the generated image URL to the caller on every
    call rather than persisting try-on history, a scope decision, not an oversight;
    add a TryOnResult table later if history/sharing is actually needed.
    """

    name = "tryon_agent"

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def provider(self) -> str:
        choice = self.settings.tryon_provider
        if choice in ("replicate", "huggingface"):
            return choice
        return "replicate" if self._replicate_configured() else "huggingface"

    def _replicate_configured(self) -> bool:
        return bool(self.settings.replicate_api_token and self.settings.replicate_tryon_model_version)

    def is_configured(self) -> bool:
        if self.provider == "huggingface":
            return StorageService().is_configured()  # the Space needs no key, but we keep its output
        return self._replicate_configured()

    def run(self, *, person_image_url: str, garment_image_url: str, **kwargs: Any) -> dict[str, Any]:
        if self.provider == "huggingface":
            return self._hf_chain(person_image_url, [(garment_image_url, "upper_body")])
        return self._try_on(person_image_url, garment_image_url, category=None)

    def run_outfit(self, *, person_image_url: str, garments: list[tuple[str, str]]) -> dict[str, Any]:
        """Dresses the person in several garments by chaining single-garment try-ons:
        each result becomes the next call's person photo. One paid Replicate call per
        garment, tens of seconds each — so callers should run it on demand and cache."""
        if not garments:
            raise RuntimeError("This outfit has no garment a try-on can dress (tops, bottoms, dresses, jackets).")
        if self.provider == "huggingface":
            return self._hf_chain(person_image_url, garments)
        current = person_image_url
        for garment_url, category in garments:
            current = self._try_on(current, garment_url, category=category)["result_image_url"]
        return {"result_image_url": current}

    def _hf_chain(self, person_image_url: str, garments: list[tuple[str, str]]) -> dict[str, Any]:
        """Runs the garments through the Hugging Face Space one after another (each
        result — a local temp file — is the next call's person photo), then stores the
        final picture and returns its URL. `persisted` tells callers it's already ours."""
        if not StorageService().is_configured():
            raise RuntimeError("Image storage isn't configured, so the try-on result can't be kept.")
        from gradio_client import Client, handle_file

        try:
            client = Client(self.settings.hf_tryon_space, hf_token=self.settings.hf_token or None, verbose=False)
            current = person_image_url
            for garment_url, category in garments:
                job = client.submit(
                    handle_file(current),
                    handle_file(garment_url),
                    HF_CATEGORY.get(category, "Upper-body"),
                    1,  # images
                    20,  # steps
                    2.0,  # guidance scale
                    -1,  # random seed
                    api_name="/process_dc",
                )
                gallery = job.result(timeout=HF_TIMEOUT_SECONDS)
                first = gallery[0]
                current = first["image"] if isinstance(first, dict) else first
        except Exception as exc:  # gradio_client raises assorted types: quota, queue, paused Space...
            raise RuntimeError(f"Hugging Face try-on failed: {_explain_hf_error(exc)}") from exc

        with open(current, "rb") as image_file:
            data = image_file.read()
        content_type = "image/png" if current.lower().endswith(".png") else "image/jpeg"
        return {"result_image_url": StorageService().upload_image(data, content_type), "persisted": True}

    def _try_on(self, person_image_url: str, garment_image_url: str, category: str | None) -> dict[str, Any]:
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
                "input": {
                    "human_img": person_image_url,
                    "garm_img": garment_image_url,
                    **({"category": category} if category and self.settings.replicate_tryon_send_category else {}),
                },
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


def _explain_hf_error(exc: Exception) -> str:
    message = str(exc)
    if "quota" in message.lower():
        return (
            f"{message} — the free GPU quota is used up; try later, or set HF_TOKEN "
            "(a free Hugging Face account) for a bigger daily quota."
        )
    return message or exc.__class__.__name__
