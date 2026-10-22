"""RAG (Retrieval-Augmented Generation) and Recommendation Service for Wardrobe Intake.

Pillars:
1. Retrieval: Cosine similarity & KNN against existing wardrobe embeddings.
2. Duplicate Detection: Detects high-similarity items already owned (similarity >= 0.82).
3. Complementary Piece Retrieval: Finds existing tops/bottoms/shoes to pair with the new item.
4. Generative AI / Prompting: Formulates structured prompts with retrieved context to produce:
   - Editorial piece description (caption)
   - Instant RAG outfit combinations with existing wardrobe pieces
   - Occasion guidance and styling advice
"""
import uuid
from typing import Any
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from app.agents.llm_agent import LLMAgent
from app.models.clothing_item import ClothingItem

# Pairs of complementary categories
COMPLEMENTARY_MAP = {
    "haut": ["bas", "veste", "chaussures", "accessoire"],
    "bas": ["haut", "veste", "chaussures", "accessoire"],
    "robe": ["veste", "chaussures", "sac", "accessoire"],
    "veste": ["haut", "bas", "chaussures"],
    "chaussures": ["haut", "bas", "robe"],
    "sac": ["robe", "haut", "bas"],
    "accessoire": ["haut", "robe", "veste"],
}


class WardrobeRAGService:
    def __init__(self, llm_agent: LLMAgent | None = None):
        self.llm_agent = llm_agent or LLMAgent()

    def analyze_wardrobe_context(
        self,
        *,
        new_embedding: np.ndarray,
        new_attributes: dict[str, Any],
        existing_items: list[ClothingItem],
        existing_embeddings: dict[uuid.UUID, np.ndarray],
    ) -> dict[str, Any]:
        """Runs KNN / Cosine similarity retrieval over existing wardrobe items."""
        category = new_attributes.get("category")
        new_vec = np.asarray(new_embedding, dtype=np.float32).reshape(1, -1)

        # 1. Duplicate / Near-Duplicate Detection (Same category, high similarity)
        similar_items = []
        for item in existing_items:
            emb = existing_embeddings.get(item.id)
            if emb is None:
                continue
            emb_vec = np.asarray(emb, dtype=np.float32).reshape(1, -1)
            sim = float(cosine_similarity(new_vec, emb_vec)[0, 0])
            if sim >= 0.70 and item.category == category:
                similar_items.append({
                    "item_id": str(item.id),
                    "image_url": item.image_url,
                    "category": item.category,
                    "colors": item.colors,
                    "style": item.style,
                    "similarity": round(sim * 100, 1),
                })

        similar_items.sort(key=lambda x: x["similarity"], reverse=True)
        duplicate_warning = None
        if similar_items and similar_items[0]["similarity"] >= 83.0:
            top_match = similar_items[0]
            duplicate_warning = (
                f"Attention : Vous possédez déjà une pièce très similaire ({top_match['similarity']}% de ressemblance) "
                f"dans votre garde-robe ({', '.join(top_match.get('colors') or [])} {top_match.get('category')})."
            )

        # 2. Complementary Piece Retrieval for RAG
        target_cats = COMPLEMENTARY_MAP.get(category or "", ["haut", "bas", "chaussures"])
        complementary_candidates = []
        for item in existing_items:
            if item.category in target_cats:
                emb = existing_embeddings.get(item.id)
                score = 0.5
                if emb is not None:
                    emb_vec = np.asarray(emb, dtype=np.float32).reshape(1, -1)
                    # Content-based similarity score (style harmony)
                    score = float(cosine_similarity(new_vec, emb_vec)[0, 0])
                # Boost if styles match
                if item.style and new_attributes.get("style") and item.style == new_attributes.get("style"):
                    score += 0.15
                complementary_candidates.append({
                    "item_id": str(item.id),
                    "category": item.category,
                    "colors": item.colors,
                    "style": item.style,
                    "image_url": item.image_url,
                    "score": round(score, 3),
                })

        complementary_candidates.sort(key=lambda x: x["score"], reverse=True)
        # Select up to 3 best complementary pieces across distinct categories
        selected_pairings = []
        seen_cats = set()
        for cand in complementary_candidates:
            if cand["category"] not in seen_cats:
                selected_pairings.append(cand)
                seen_cats.add(cand["category"])
                if len(selected_pairings) >= 3:
                    break

        return {
            "duplicate_warning": duplicate_warning,
            "similar_items": similar_items[:3],
            "recommended_pairings": selected_pairings,
        }

    def generate_styling_insights(
        self,
        *,
        attributes: dict[str, Any],
        rag_context: dict[str, Any],
        palette: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Prompt-engineered LLM generation with fallback expert styling engine."""
        category = attributes.get("category") or "vêtement"
        style = attributes.get("style") or "Casual"
        colors = attributes.get("colors") or []
        pattern = attributes.get("pattern") or "uni"
        season = attributes.get("season") or "toutes saisons"
        dominant_colors_str = ", ".join(colors) if colors else "neutre"

        retrieved_pairings = rag_context.get("recommended_pairings", [])
        pairings_desc = ""
        if retrieved_pairings:
            pairings_desc = "Pièces existantes recommandées dans le dressing pour l'associer : " + "; ".join(
                f"{p['category']} ({', '.join(p.get('colors') or [])}, style {p.get('style')})"
                for p in retrieved_pairings
            )
        else:
            pairings_desc = "Aucune pièce complémentaire actuellement trouvée dans le dressing."

        # Prompt construction
        prompt_instruction = (
            f"Tu es un styliste de mode IA haut de gamme pour l'application DressMe. "
            f"Une nouvelle pièce vient d'être ajoutée à la garde-robe : un {category} ({dominant_colors_str}, motif: {pattern}, style: {style}, saison: {season}).\n"
            f"Contexte RAG de sa garde-robe : {pairings_desc}\n"
            f"Rédige en français un conseil stylistique structuré comprenant :\n"
            f"1. Une brève description éditoriale flatteuse de la pièce.\n"
            f"2. Des idées concrètes d'associations de tenues avec les pièces déjà possédées.\n"
            f"3. Les occasions idéales (ex: Travail, Soirée, Détente).\n"
            f"4. Un conseil d'entretien du tissu."
        )

        llm_result = self.llm_agent.run(
            context={
                "category": category,
                "style": style,
                "colors": colors,
                "season": season,
                "retrieved_pairings": retrieved_pairings,
            },
            instruction=prompt_instruction,
        )

        editorial_advice = llm_result.get("explanation")

        # Fallback expert system if LLM provider is none or returned null
        if not editorial_advice:
            editorial_advice = self._generate_rule_based_editorial(
                category=category,
                style=style,
                colors=colors,
                pattern=pattern,
                season=season,
                retrieved_pairings=retrieved_pairings,
                palette=palette,
            )

        return {
            "editorial_advice": editorial_advice,
            "style_archetype": style,
            "recommended_occasions": self._infer_occasions(style),
            "care_tip": self._care_tip_for_category(category),
        }

    def _generate_rule_based_editorial(
        self,
        category: str,
        style: str,
        colors: list[str],
        pattern: str,
        season: str,
        retrieved_pairings: list[dict],
        palette: list[dict],
    ) -> str:
        color_str = " ".join(colors) if colors else "neutre"
        lines = [
            f"[Style {style}] : Superbe {category} {color_str} ({pattern}). Une piece essentielle ideale pour la saison {season}.",
        ]
        if retrieved_pairings:
            pair_items = [f"{p['category']} ({', '.join(p.get('colors') or [])})" for p in retrieved_pairings]
            lines.append(
                f"[Conseil d'association RAG] : Mariez cette piece directement avec vos elements de garde-robe : {', '.join(pair_items)} pour une silhouette equilibree."
            )
        else:
            lines.append(
                f"[Conseil d'association] : Associez-la avec des tons contrastes ou monochromes selon l'occasion."
            )

        top_palette = [p["label"] for p in palette[:2] if p.get("label")]
        if top_palette:
            lines.append(f"[Harmonie des couleurs] : Dominante {', '.join(top_palette)}.")

        return "\n\n".join(lines)

    def _infer_occasions(self, style: str) -> list[str]:
        s = (style or "").lower()
        if "formal" in s or "chic" in s:
            return ["Bureau & Business", "Dîner officiel", "Événement habillé"]
        if "sport" in s:
            return ["Séance sportive", "Sortie active", "Week-end relax"]
        if "party" in s:
            return ["Soirée entre amis", "Fête", "Sortie nocturne"]
        return ["Quotidien / Ville", "Déjeuner décontracté", "Télétravail"]

    def _care_tip_for_category(self, category: str) -> str:
        cat = (category or "").lower()
        if cat in ["veste"]:
            return "Nettoyage à sec recommandé ou aération sur cintre après port."
        if cat in ["chaussures"]:
            return "Nettoyer avec un chiffon humide et nourrir la matière régulièrement."
        if cat in ["sac", "accessoire"]:
            return "Conserver dans un pochon à l'abri de la lumière directe."
        return "Lavage délicat à 30°C sur l'envers pour préserver les couleurs et les fibres."
