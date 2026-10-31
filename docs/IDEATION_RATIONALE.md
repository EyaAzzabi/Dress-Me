# Ideation → Persona → Objective traceability

Built from `docs/Copie de user persona architecture (1).pdf` (personas p.8–12, business
objectives p.14, data science objectives p.15, idées proposées p.16) to answer the
question a Validation Ideation checkpoint typically asks: **why these ideas, and not
others?**

| Idée proposée | Personas served | Business objective | Data Science objective |
|---|---|---|---|
| **Smart Wardrobe** | Lina (rediscover her wardrobe), Maha (a global view of everything she owns) | 01 — Maximize value of existing wardrobe | 01 Attribute extraction, 02 Vector representation |
| **Smart Outfit** | Lina (vary daily outfits with what she owns), Ahmed (doesn't know which combo to pick) | 01 — Maximize value of existing wardrobe | 02 Vector representation, 05 Personalized outfit ranking |
| **Context-Aware Styling** | Ahmed (formality/occasion/constraints) | 02 — Personalized fashion experience | 04 Contextual modeling |
| **Style Learning** | Lina (find a look that resembles her), Iskander (discover styles he likes) | 02 — Personalized fashion experience | 03 Dynamic user-profile modeling |
| **Should I Buy This?** | All personas — directly answers the core problem statement ("exploiter d'abord, acheter intelligemment ensuite") | 01 — Maximize wardrobe value, 03 — Favor intentional purchases | 02 Vector representation, 06 Wardrobe gap detection |
| **Wardrobe Gap Detection** | Ahmed (real, unmet needs vs. what he already owns) | 03 — Favor intentional purchases | 06 Wardrobe gap detection |
| **Local Fashion Matching** | (supply-side, triggered by Wardrobe Gap Detection) | 05 — Valorize the Tunisian fashion ecosystem | — (relies on the Tunisian catalog data source) |
| **Virtual Try-On** *(future exploration, not committed)* | Iskander explicitly ("l'avatar peut l'aider à se projeter, mais son expérience reste décisive") | 02 — Personalized fashion experience | — |

## Open question this table surfaces

**Karim (the retailer/boutique persona) has no corresponding idea.** His stated needs —
organize stock/sizes/quantities, link stock to outfit ideas, see real available
inventory — are all B2B/supply-side, and none of the 7 consumer-facing ideas address
them. `Local Fashion Matching` touches Tunisian brands only from the *consumer's*
discovery side, not from a retailer's stock-management side.

Two ways to close this before validation:
1. **Explicit scope decision**: state that Karim is out of scope for this iteration
   (DressMe v1 is B2C only) and note it as a documented limitation, not an oversight.
2. **Add an idea**: a lightweight retailer-facing feature (e.g. a stock feed that
   powers `Local Fashion Matching` instead of manual scraping) — bigger scope increase,
   probably not worth it before this checkpoint.

Recommendation: option 1 — say it explicitly in the validation session rather than
leaving it implicit. Reviewers notice personas with no corresponding feature; framing it
as a conscious scope call is stronger than looking like it was missed.
