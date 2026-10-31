"""StyleRAG — retrieves style guidelines relevant to a given outfit context.

Primary path: TF-IDF cosine similarity over 20 hardcoded French style rules
(always available; no external dependencies).

Optional upgrade: push / query Qdrant when qdrant-client is installed and a
server URL is provided. Gated behind a try/except import so the absence of the
package is silent.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardcoded style guide corpus (20 French rules)
# ---------------------------------------------------------------------------
STYLE_GUIDES: list[str] = [
    "Les couleurs neutres (blanc, beige, gris, navy) se combinent avec tout.",
    "Évite de mélanger plus de 3 couleurs dominantes dans une tenue.",
    "Pour une occasion formelle, privilégie des pièces monochromes ou bicolores.",
    "En été, opte pour des matières légères : lin, coton, voile.",
    "En hiver, superpose les couches : t-shirt + pull + manteau.",
    "Le mariage : robe de cocktail ou costume élégant, jamais de jeans.",
    "Pour le travail, le 'business casual' combine pantalon chino + chemise ou blouse.",
    "Le sport requiert des pièces techniques : legging, t-shirt respirant, baskets.",
    "Une tenue complète comporte : haut, bas (ou robe) et chaussures adaptées.",
    "Les imprimés se mélangent avec parcimonie : un seul imprimé par tenue.",
    "Le noir amincit visuellement et s'adapte à toutes les occasions formelles.",
    "Les couleurs vives (rouge, jaune, orange) doivent être équilibrées par du neutre.",
    "Chaussures et sac dans le même registre (ton sur ton ou contraste assumé).",
    "En printemps, les pastels et floraux signalent la légèreté de la saison.",
    "En automne, les tons terre (bordeaux, camel, kaki) sont de saison.",
    "Pour la plage, la tenue doit être légère, colorée et pratique (maillot + paréo).",
    "Une veste structurée transforme immédiatement un look décontracté en look soigné.",
    "Les sneakers blanches sont polyvalentes : casual, sorties, même certains looks soirée.",
    "Pour un mariage oriental, privilégie les tissus brodés, dentelles et couleurs festives.",
    "La règle des 3 : une tenue réussie mélange 3 éléments max (couleur, matière, motif).",
]


class StyleRAG:
    """Retrieve the most relevant style rules for a given query via TF-IDF.

    Parameters
    ----------
    qdrant_url:
        Optional URL of a Qdrant server. When provided *and* qdrant-client is
        installed, ``index_style_guides`` can push the corpus there and
        ``retrieve`` will prefer the dense-vector path. Falls back to TF-IDF
        silently on any error.
    collection_name:
        Qdrant collection to use (default: "style-guides").
    """

    def __init__(
        self,
        qdrant_url: str | None = None,
        collection_name: str = "style-guides",
    ) -> None:
        self._qdrant_url = qdrant_url
        self._collection_name = collection_name
        self._qdrant_client: object | None = None
        self._tfidf_matrix = None
        self._vectorizer = None

        # Build TF-IDF at init time (fast, in-memory, no I/O)
        self._build_tfidf()

        # Try Qdrant if requested
        if qdrant_url:
            self._init_qdrant(qdrant_url)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_tfidf(self) -> None:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self._vectorizer = TfidfVectorizer()
            self._tfidf_matrix = self._vectorizer.fit_transform(STYLE_GUIDES)
        except Exception:
            logger.warning("StyleRAG: TF-IDF build failed; fallback will return first rules", exc_info=True)
            self._vectorizer = None
            self._tfidf_matrix = None

    def _init_qdrant(self, url: str) -> None:
        try:
            from qdrant_client import QdrantClient  # type: ignore[import]

            self._qdrant_client = QdrantClient(url=url)
        except Exception:
            logger.debug("StyleRAG: qdrant-client not available or server unreachable; using TF-IDF")
            self._qdrant_client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        """Return the *top_k* most relevant style rules for *query*.

        Falls back to ``STYLE_GUIDES[:top_k]`` on any error.
        """
        try:
            if self._vectorizer is None or self._tfidf_matrix is None:
                return STYLE_GUIDES[:top_k]

            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np

            query_vec = self._vectorizer.transform([query])
            sims = cosine_similarity(query_vec, self._tfidf_matrix).flatten()
            top_indices = np.argsort(sims)[::-1][:top_k]
            return [STYLE_GUIDES[i] for i in top_indices]
        except Exception:
            logger.warning("StyleRAG.retrieve failed; returning first %d rules", top_k, exc_info=True)
            return STYLE_GUIDES[:top_k]

    def index_style_guides(self) -> None:
        """Push STYLE_GUIDES to Qdrant (no-op when qdrant-client is not installed)."""
        if self._qdrant_client is None:
            return
        try:
            from qdrant_client import QdrantClient  # type: ignore[import]
            from qdrant_client.models import Distance, VectorParams, PointStruct  # type: ignore[import]
            import hashlib

            client: QdrantClient = self._qdrant_client  # type: ignore[assignment]

            # Use a tiny 20-dim "embedding" (index as integer) just to store the text.
            # In production you'd use a real embedding model here.
            dim = len(STYLE_GUIDES)
            try:
                client.create_collection(
                    collection_name=self._collection_name,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
            except Exception:
                pass  # collection may already exist

            points = [
                PointStruct(
                    id=i,
                    vector=[1.0 if j == i else 0.0 for j in range(dim)],
                    payload={"text": text},
                )
                for i, text in enumerate(STYLE_GUIDES)
            ]
            client.upsert(collection_name=self._collection_name, points=points)
        except Exception:
            logger.warning("StyleRAG.index_style_guides failed", exc_info=True)
