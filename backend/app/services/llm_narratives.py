"""Evidence-bound French plans. The LLM selects IDs; Python renders every fact.

Unrestricted paraphrasing cannot enforce a no-hallucination contract. Selection of
verified sentence variants preserves personalization without trusting model prose.
"""
from dataclasses import dataclass
import json
import re
from typing import Any


def label(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[<>\x00-\x1f\x7f]", "", value).strip()[:100]


def labels(values: Any) -> list[str]:
    return [text for value in (values or []) if (text := label(value))]


@dataclass(frozen=True)
class NarrativePlan:
    choices: dict[str, list[str]]
    required: tuple[str, ...]

    def response_format(self) -> dict[str, Any]:
        """Schema constrains syntax; render() additionally enforces evidence rules."""
        return {"type": "json_schema", "json_schema": {
            "name": "dressme_narrative", "strict": True, "schema": {
                "type": "object", "additionalProperties": False,
                "properties": {"sentences": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {"fact": {"type": "string", "enum": list(self.choices)},
                                   "variant": {"type": "integer", "enum": [0, 1]}},
                    "required": ["fact", "variant"]}}}, "required": ["sentences"]}}}

    def render(self, content: str) -> str:
        data = json.loads(content)
        if not isinstance(data, dict) or set(data) != {"sentences"}:
            raise ValueError("Expected only sentences")
        rows = data["sentences"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
            raise ValueError("Invalid sentence count")
        seen, rendered = set(), []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"fact", "variant"}:
                raise ValueError("Invalid sentence selection")
            fact, variant = row["fact"], row["variant"]
            if not isinstance(fact, str) or fact not in self.choices or fact in seen:
                raise ValueError("Unknown or repeated fact")
            if type(variant) is not int or not 0 <= variant < len(self.choices[fact]):
                raise ValueError("Invalid variant")
            seen.add(fact)
            rendered.append(self.choices[fact][variant])
        if not set(self.required) <= seen or (self.required and rows[0]["fact"] != self.required[0]):
            raise ValueError("Missing required evidence or lead")
        text = " ".join(rendered)
        if len(text) > 2048:
            raise ValueError("Narrative exceeds persistence limit")
        return text


def build_plan(task: str, facts: dict[str, Any]) -> NarrativePlan:
    choices: dict[str, list[str]] = {}
    if task == "style_profile":
        n = facts.get("wardrobe_size")
        if type(n) is not int or n < 1:
            raise ValueError("No wardrobe facts")
        choices["composition"] = [f"Ta garde-robe compte {n} pièces.",
                                  f"Avec {n} pièces, voici le portrait de ta garde-robe."]
        counts = facts.get("category_counts", {})
        parts = [f"{count} {label(category)}" for category, count in sorted(counts.items())
                 if label(category) and type(count) is int and count > 0]
        if parts:
            choices["categories"] = ["Sa composition : " + ", ".join(parts) + "."]
        colors, styles = labels(facts.get("favorite_colors")), labels(facts.get("favorite_styles"))
        if colors:
            choices["colors"] = ["Les couleurs les plus présentes sont : " + ", ".join(colors) + ".",
                                 "Côté couleurs, " + ", ".join(colors) + " reviennent le plus souvent."]
        if styles:
            choices["styles"] = ["Les styles dominants sont : " + ", ".join(styles) + ".",
                                 "Tes pièces font surtout ressortir ces styles : " + ", ".join(styles) + "."]
        return NarrativePlan(choices, ("composition",))
    if task == "outfit":
        items = facts.get("items", [])
        if not items:
            raise ValueError("No outfit pieces")
        pieces = []
        for item in items:
            category = label(item.get("category")) or "pièce"
            colors = labels(item.get("colors"))
            pieces.append(category + (" (" + ", ".join(colors) + ")" if colors else ""))
        choices["composition"] = ["Cette tenue associe : " + ", ".join(pieces) + ".",
                                  "Pour cette tenue, combine ces pièces de ta garde-robe : " + ", ".join(pieces) + "."]
        top = next(iter(labels(facts.get("favorite_styles"))), None)
        if top and all(item.get("style") == top for item in items):
            choices["style"] = [f"Toutes ces pièces partagent ton style dominant : {top}."]
        context = facts.get("context", {})
        for key, prefix in (("occasion", "Occasion demandée"), ("season", "Saison sélectionnée"),
                            ("weather", "Météo fournie")):
            if value := label(context.get(key)):
                choices[key] = [f"{prefix} : {value}."]
        # The upstream algorithm does not validate dress codes/weather suitability.
        return NarrativePlan(choices, ("composition",))
    if task == "purchase":
        leads = {"recommended": ["Cet achat est recommandé par l'analyse.", "L'analyse est favorable à cet achat."],
                 "think_twice": ["Cet achat mérite réflexion.", "L'analyse invite à réfléchir avant cet achat."],
                 "not_recommended": ["Cet achat n'est pas recommandé.", "L'analyse déconseille cet achat."]}
        choices["verdict"] = leads[facts["verdict"]]
        required = ["verdict"]
        # Trusted upstream rationale includes evidence limitations; always preserve it.
        if isinstance(facts.get("explanation"), str) and facts["explanation"].strip():
            choices["reason"] = [facts["explanation"].strip()[:1000]]
            required.append("reason")
        if facts.get("duplicates"):
            choices["duplicates"] = ["Une pièce similaire a déjà été repérée dans ta garde-robe."]
            required.append("duplicates")
        n = facts.get("outfits_unlocked")
        if type(n) is int and n >= 0 and facts.get("has_wardrobe_evidence"):
            choices["outfits"] = [f"L'analyse calcule {n} associations possibles avec tes vêtements existants."]
            required.append("outfits")
        price = facts.get("price")
        if type(price) in (int, float) and price > 0:
            choices["price"] = [f"Le prix renseigné est de {price:g} TND."]
            required.append("price")
        choices["policy"] = ["Privilégie ce que tu possèdes déjà ; achète seulement si cela répond à un besoin."]
        required.append("policy")
        return NarrativePlan(choices, tuple(required))
    raise ValueError("Unsupported narrative task")
