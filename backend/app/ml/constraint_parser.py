"""Constraint Parser — Extract style/color/occasion constraints from French text.

Uses Ollama (Mistral) via httpx for LLM-based parsing, with a deterministic
regex fallback when LLM is unavailable or fails.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Module-level counters for LLM vs fallback success tracking
_parser_stats = {
    "llm_success": 0,
    "regex_fallback": 0,
    "last_reset": time.time(),
    "recent_fallbacks": [],  # list of (timestamp, constraint_text, reason)
}

# French color keywords for fallback parsing
_FRENCH_COLORS = {
    "bleu", "rouge", "vert", "noir", "blanc", "rose", "beige", "jaune", 
    "orange", "violet", "gris", "marron", "marine", "bordeaux", 
    "turquoise", "doré", "argenté", "cyan", "magenta", "lime", "indigo"
}

# French style keywords for fallback parsing
_FRENCH_STYLES = {
    "casual", "élégant", "formel", "sport", "chic", "bohème", "classique",
    "décontracté", "sophistiqué", "preppy", "vintage", "moderne", "minimaliste",
    "baroque", "sportif", "street"
}

# French occasion keywords for fallback parsing
_FRENCH_OCCASIONS = {
    "soirée", "travail", "sport", "mariage", "plage", "ville", "quotidien",
    "fête", "réunion", "rendez-vous", "gym", "yoga", "running", "randonnée",
    "concert", "cinéma", "restaurant", "bar", "brunch", "dîner"
}

# Formality keywords
_FORMALITY_KEYWORDS = {
    "formel": "formal",
    "très formel": "formal",
    "décontracté": "casual",
    "très décontracté": "casual",
    "smart casual": "smart_casual",
    "semi-formel": "smart_casual",
    "business casual": "smart_casual",
}

# Season keywords
_SEASON_KEYWORDS = {
    "printemps": "printemps",
    "été": "été",
    "automne": "automne",
    "hiver": "hiver",
    "spring": "printemps",
    "summer": "été",
    "fall": "automne",
    "autumn": "automne",
    "winter": "hiver",
}


def _add_fallback_event(constraint_text: str, reason: str) -> None:
    """Record a fallback event in the recent_fallbacks list (keep last 10)."""
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "constraint_text": constraint_text[:100],  # Limit text length
        "reason": reason,
    }
    _parser_stats["recent_fallbacks"].append(event)
    # Keep only last 10 events
    if len(_parser_stats["recent_fallbacks"]) > 10:
        _parser_stats["recent_fallbacks"] = _parser_stats["recent_fallbacks"][-10:]


class ConstraintParser:
    """Extracts style/color/occasion constraints from user text in French.
    
    Attributes:
        llm_url: Base URL for the LLM service (Ollama). Default: http://localhost:11434/v1
        model: Model name. Default: mistral
        timeout: HTTP timeout in seconds. Default: 5.0
    """

    def __init__(
        self,
        *,
        llm_url: str = "http://localhost:11434/v1",
        model: str = "mistral",
        timeout: float = 1.0,
        settings: Any | None = None,
    ) -> None:
        self.llm_url = llm_url
        self.model = model
        self.timeout = timeout
        self.settings = settings

    def parse(self, request_text: str | None) -> dict[str, Any]:
        """Parse constraints from request_text using LLM with regex fallback.
        
        Args:
            request_text: User's request in French (or None/empty).
        
        Returns:
            Dict with keys: colors, styles, occasions, formality, season, notes.
            All lists are lists of strings; optional fields are None or empty.
            Never raises; always returns a valid dict.
        """
        if not request_text or not isinstance(request_text, str) or not request_text.strip():
            return self._empty_constraints()

        try:
            # Try LLM path first
            constraints = self._parse_with_llm(request_text)
            if constraints:
                _parser_stats["llm_success"] += 1
                logger.info(
                    "Constraint extraction: LLM=success, colors=%s, styles=%s, occasion=%s",
                    constraints.get("colors"),
                    constraints.get("styles"),
                    constraints.get("occasions"),
                )
                logger.debug("Constraint parsing succeeded (LLM): %s", constraints)
                return constraints
        except Exception as exc:
            logger.debug("Constraint parsing LLM failed: %s", exc)

        # Fallback to regex
        try:
            constraints = self._parse_with_regex(request_text)
            _parser_stats["regex_fallback"] += 1
            reason = "LLM unavailable or failed"
            _add_fallback_event(request_text, reason)
            logger.warning(
                "Constraint extraction: fallback triggered (reason=%s), colors=%s, styles=%s",
                reason,
                constraints.get("colors"),
                constraints.get("styles"),
            )
            logger.debug("Constraint parsing succeeded (regex fallback): %s", constraints)
            return constraints
        except Exception as exc:
            logger.warning("Constraint parsing fallback failed: %s", exc)
            return self._empty_constraints()

    def _parse_with_llm(self, text: str) -> dict[str, Any] | None:
        """Call Mistral via Ollama to extract constraints.
        
        Returns:
            Parsed constraints dict, or None if parsing failed.
            Raises on HTTP errors.
        """
        try:
            import httpx
        except ImportError:
            logger.debug("httpx not available; skipping LLM path")
            return None

        system_prompt = (
            "Tu es un assistant stylistique expert en mode française. "
            "Extrait les contraintes de style de ce texte et retourne uniquement un JSON avec les champs: "
            "colors (liste de couleurs en français), styles (liste de styles en français), "
            "occasions (liste d'occasions en français), formality (str: casual/smart_casual/formal/null), "
            "season (str: printemps/été/automne/hiver/null), notes (str|null pour notes additionnelles). "
            "Exemples: "
            "'touche de bleu' -> {\"colors\":[\"bleu\"], ...}, "
            "'soirée élégante' -> {\"occasions\":[\"soirée\"], \"formality\":\"formal\", ...}, "
            "'style casual' -> {\"styles\":[\"casual\"], ...}. "
            "Retourne un JSON valide, rien d'autre."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "temperature": 0.7,
        }

        try:
            response = httpx.post(
                f"{self.llm_url}/chat/completions",
                json=payload,
                timeout=httpx.Timeout(self.timeout, connect=1.0),
            )
            response.raise_for_status()
            result = response.json()
            raw_response = result.get("message") or result.get("choices", [{}])[0].get("message", {})
            content = raw_response.get("content", "")
            
            # Parse JSON from response
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from the response
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    parsed = json.loads(content[start:end])
                else:
                    return None

            return self._normalize_output(parsed)
        except Exception as exc:
            logger.debug("LLM parse error: %s", exc)
            raise

    def _parse_with_regex(self, text: str) -> dict[str, Any]:
        """Deterministic regex-based fallback parser."""
        text_lower = text.lower()
        
        colors = []
        styles = []
        occasions = []
        formality = None
        season = None

        # Extract colors
        for color in _FRENCH_COLORS:
            # Match "touche de bleu", "bleu et", "en bleu", "de bleu", or standalone
            if re.search(rf"\b{re.escape(color)}\b", text_lower):
                colors.append(color)

        # Extract styles
        for style in _FRENCH_STYLES:
            if re.search(rf"\b{re.escape(style)}\b", text_lower):
                styles.append(style)

        # Extract occasions
        for occasion in _FRENCH_OCCASIONS:
            if re.search(rf"\b{re.escape(occasion)}\b", text_lower):
                occasions.append(occasion)

        # Extract formality
        for keyword, val in _FORMALITY_KEYWORDS.items():
            if keyword in text_lower:
                formality = val
                break

        # Extract season
        for keyword, val in _SEASON_KEYWORDS.items():
            if keyword in text_lower:
                season = val
                break

        return {
            "colors": list(set(colors)),  # Deduplicate
            "styles": list(set(styles)),
            "occasions": list(set(occasions)),
            "formality": formality,
            "season": season,
            "notes": None,
        }

    def _normalize_output(self, raw_dict: dict[str, Any]) -> dict[str, Any]:
        """Normalize and validate LLM output to constraint schema."""
        def to_list(val: Any, name: str = "item") -> list[str]:
            if val is None:
                return []
            if isinstance(val, str):
                return [val] if val.strip() else []
            if isinstance(val, list):
                return [str(v).strip().lower() for v in val if v and str(v).strip()]
            return []

        def to_str_or_none(val: Any) -> str | None:
            if val is None:
                return None
            s = str(val).strip().lower()
            return s if s else None

        return {
            "colors": to_list(raw_dict.get("colors")),
            "styles": to_list(raw_dict.get("styles")),
            "occasions": to_list(raw_dict.get("occasions")),
            "formality": to_str_or_none(raw_dict.get("formality")),
            "season": to_str_or_none(raw_dict.get("season")),
            "notes": to_str_or_none(raw_dict.get("notes")),
        }

    @staticmethod
    def _empty_constraints() -> dict[str, Any]:
        """Return an empty/default constraints dict."""
        return {
            "colors": [],
            "styles": [],
            "occasions": [],
            "formality": None,
            "season": None,
            "notes": None,
        }

    @classmethod
    def get_stats(cls) -> dict[str, Any]:
        """Get current parser statistics.
        
        Returns:
            Dict with keys: success, fallback, fallback_rate, last_reset, recent_fallbacks
        """
        total = _parser_stats["llm_success"] + _parser_stats["regex_fallback"]
        fallback_rate = (
            _parser_stats["regex_fallback"] / total if total > 0 else 0.0
        )
        return {
            "success": _parser_stats["llm_success"],
            "fallback": _parser_stats["regex_fallback"],
            "fallback_rate": fallback_rate,
            "last_reset": _parser_stats["last_reset"],
            "recent_fallbacks": _parser_stats["recent_fallbacks"][-10:],  # Last 10
        }

    @classmethod
    def reset_stats(cls) -> None:
        """Reset all counters and recent fallbacks."""
        _parser_stats["llm_success"] = 0
        _parser_stats["regex_fallback"] = 0
        _parser_stats["last_reset"] = time.time()
        _parser_stats["recent_fallbacks"] = []
