# Vision Agent — explication technique (pour l'oral)

> Les fichiers de code contiennent des commentaires `[Oral]` : cherche ce mot dans l'éditeur (Ctrl+Maj+F)
> pour retrouver, dans l'ordre de lecture, tous les points à expliquer.

## 1. En une phrase

Le Vision Agent est **les yeux de DressMe** : à partir de la photo d'un vêtement, il devine sa **catégorie**,
ses **couleurs**, son **motif**, son **style** et sa **saison**, avec un **niveau de confiance** pour chaque
valeur, et il produit un **embedding** (512 nombres) qui sert ensuite à comparer les vêtements entre eux.

## 2. L'idée centrale : l'embedding

On transforme la photo en une liste de 512 nombres avec le modèle **FashionCLIP** (CLIP, réentraîné sur des
photos de mode). Propriétés importantes :

- deux vêtements qui se ressemblent donnent deux listes proches (mesure : similarité cosinus) ;
- le même modèle transforme aussi du **texte** en 512 nombres **dans le même espace** : on peut donc demander
  « cette photo ressemble-t-elle à la phrase *a striped garment* ? ».

On calcule l'embedding **une seule fois**, puis tous les attributs en sont déduits, sans ré-analyser la photo.

```
photo ──FashionCLIP──► embedding (512 nombres) ─┬─► catégorie    2 classifieurs ENTRAÎNÉS par nous
                                                ├─► couleurs     zero-shot (comparaison à des phrases)
                                                ├─► motif        zero-shot
                                                ├─► style/saison via le TYPE de vêtement (priors appris)
                                                └─► (stocké dans Pinecone : recherche de similarité)
```

## 3. Où est quoi (fichiers)

| Fichier | Rôle |
|---|---|
| `backend/app/agents/vision_agent.py` | L'agent : télécharge la photo, vérifie (taille, image valide), délègue. Aucune IA ici. |
| `backend/app/ml/vision_model.py` | **Le cœur** : FashionCLIP, embedding, zero-shot, `predict_*`, et `analyze_image` qui assemble tout. |
| `backend/app/ml/garment_types.py` | Saison et style déduits du **type** de vêtement (formule + tableaux appris). |
| `backend/app/ml/clothing_gate.py` | « Est-ce même un vêtement ? » (rejette paysages, visages, captures d'écran). |
| `backend/app/ml/vision_llm.py` | Avis **optionnel** de GPT-4o-mini (prompt CRISPE versionné) pour le style, si FashionCLIP hésite. |
| `backend/app/ml/artifacts/category_classifier.joblib` | Le « portier » entraîné (8 classes dont `hors_perimetre`). |
| `backend/app/ml/artifacts/garment_category_classifier.joblib` | La « tête garment » entraînée (SVM, 7 catégories). |
| `backend/app/ml/artifacts/garment_type_priors.json` | Tendances type → saison / style (fabriquées à partir de 44 000 produits). |
| `backend/app/agents/wardrobe_ingestion_agent.py` | Chaîne complète d'ajout d'un vêtement (qualité de la photo, palette K-Means, segmentation, RAG) ; appelle `vision_model.analyze_image`. |
| `backend/app/api/routes/wardrobe.py` | Les routes `POST /wardrobe/analyze` et `POST /wardrobe/` (gère aussi la confirmation de catégorie). |
| `backend/app/agents/metadata_agent.py` | Enregistre ensuite le vêtement en base et l'embedding dans Pinecone. |
| `backend/app/agents/orchestrator.py` | Utilise `VisionAgent.run` pour le flux « vérifier un achat ». |
| `ml/notebooks/08, 11, 12, 13, 14, 15` | Entraînement et évaluation (voir §6). |
| `ml/reports/vision_agent_evaluation.md`, `vision_prompt_versions.md` | Résultats mesurés. |
| `backend/tests/test_vision_*.py`, `test_clothing_gate.py`, `test_low_category_confidence.py` | Tests. |

## 4. Le parcours d'une photo (de l'app à la base de données)

1. L'app envoie la photo : `POST /wardrobe/upload` (stockage) puis `POST /wardrobe/` avec l'URL.
2. La route lance le `WardrobeIngestionAgent`, qui appelle `vision_model.analyze_image` :
   1. `embed_image_bytes` : photo → embedding (512 nombres) ;
   2. `predict_category` : portier, puis tête garment ;
   3. `predict_colors`, `predict_pattern` : zero-shot ;
   4. `predict_style`, `predict_season` : via `garment_types` ;
   5. si le style est inconnu **et** l'option activée : avis de GPT-4o-mini (`vision_llm`).
3. Si la photo n'est pas un vêtement (`hors_perimetre`) : erreur 422.
4. Si la confiance de la catégorie est **< 60 %** (souvent une photo de plusieurs vêtements) : erreur 422
   `low_category_confidence` ; l'app demande à l'utilisateur de **confirmer la catégorie**, puis renvoie la photo.
5. Sinon le `MetadataAgent.add_item` enregistre le vêtement (PostgreSQL) et l'embedding (Pinecone).

## 5. Les trois techniques d'IA utilisées (à bien distinguer)

### a) Zero-shot (couleur, motif) — aucune donnée d'entraînement
On écrit une phrase par valeur possible, on mesure la ressemblance photo/phrase, puis un **softmax** transforme les
scores en probabilités. La plus grande probabilité est la réponse **et** la confiance (`_zero_shot_probs`).

### b) Apprentissage supervisé sur embeddings gelés (catégorie)
On **n'entraîne pas** FashionCLIP (trop lourd sans GPU) : on l'utilise comme extracteur de caractéristiques et on
entraîne par-dessus de petits classifieurs :

- **portier** (régression logistique, 8 classes) : vêtement ou non ;
- **tête garment** (SVM à noyau RBF, 7 classes) : quelle catégorie.

Données : ~8 900 photos de boutiques tunisiennes (4 636 vêtements), découpées en **entraînement / validation /
test**. Les réglages (valeur de `C`, type de modèle) sont choisis sur la validation ; le test ne sert qu'à
rapporter les résultats. Le modèle livré est ensuite réentraîné sur entraînement + validation.

### c) Saison et style « via le type de vêtement »
FashionCLIP reconnaît bien « un short » ou « un pull » mais mal « un vêtement d'été » (46 % de justesse, **moins que
répondre toujours « été »**). On classe donc d'abord le **type** (≈40 types), et chaque type porte une tendance apprise
sur 44 000 produits (ex. *pull* : été 5 %, hiver 11 %, mi-saison 85 %) :

`P(saison | photo) = Σ_types P(type | photo) × tendance(type → saison)`

### d) (Option) LLM multimodal avec prompt CRISPE
`vision_llm.py` envoie la photo à GPT-4o-mini avec un prompt structuré CRISPE (**C**apacity/Role, **I**nsight,
**S**tatement, **P**ersonality, **E**xperiment). Désactivé par défaut. Chaque réponse est **validée** contre nos listes de
valeurs (on ne fait jamais confiance à un LLM). Les prompts sont **versionnés** (v1 à v5) et gelés une fois mesurés.

## 6. Résultats mesurés (avec honnêteté)

| Sujet | Résultat | Fiabilité |
|---|---|---|
| Catégorie, vêtements gardés par le portier | 85,2 % → **87,0 %** (+1,8 pt) | IC 95 % [−0,4 ; +4,2] : **non significatif** |
| Robes | F1 0,77 → 0,86 | meilleure ; les vestes baissent (0,76 → 0,71) |
| Saison (précision équilibrée) | 0,35 → **0,48** | IC [+0,05 ; +0,20] : significatif, mais **plafond bas** (étiquettes de collection, pas du visible) |
| Style (précision équilibrée) | 0,64 → **0,78** | IC [+0,05 ; +0,22] |
| Couleur | ~70 % (inchangé) | essais d'amélioration sans effet fiable |
| Avis GPT sur le style (là où FashionCLIP hésite) | 89,5 % contre 39,5 % | mais ces photos sont à 80 % « Casual » : le gain réel est ≈ 9 pts |
| Prompts CRISPE v1 → v5 | v1 reste la meilleure pour le style | le vrai gain : correctif de code (0 échec sur 3 500 appels) |

Seuils de confiance (catégorie 0,60 ; style 0,70 ; saison 0,60) : choisis **en mesurant** sur des photos étiquetées.
Sous le seuil, l'agent répond `None` plutôt qu'une valeur hasardeuse.

## 7. Questions probables du professeur

**Pourquoi pas de fine-tuning de FashionCLIP ?**
Cela demande un GPU et beaucoup de données. Nous avons entraîné des classifieurs sur l'embedding gelé (*linear probe*
et SVM), faisable sur processeur. Le fine-tuning complet ou LoRA est une suite possible sur Colab.

**Qu'est-ce que le zero-shot ?**
Classer sans exemples d'entraînement : on décrit chaque classe par une phrase et on prend celle qui ressemble le plus
à la photo, dans l'espace commun image/texte de CLIP.

**Comment savez-vous que ça marche ?**
Découpage entraînement / validation / test ; réglages sur la validation ; résultats sur le test ; **intervalles de
confiance par bootstrap** ; comparaison « avant / après » sur les mêmes photos (`ml/notebooks/13`).

**Pourquoi un seuil de confiance ?**
Mieux vaut demander confirmation à l'utilisateur que de polluer sa garde-robe avec une catégorie fausse (sinon les
recommandations en souffrent).

**Pourquoi deux classifieurs pour la catégorie ?**
Le portier doit aussi dire « pas un vêtement » ; le SVM, entraîné uniquement sur des vêtements, se concentre sur la
distinction entre catégories. Gain modeste, que nous rapportons tel quel.

**Quelles limites ?**
Photos de catalogue (un article par photo) : des photos de téléphone peuvent donner d'autres scores. La saison et le
style reposent sur des étiquettes imparfaites (300 photos pour mesurer). Le motif n'a pas de vérité terrain. Le LLM
envoie la photo à OpenAI (confidentialité) : désactivé par défaut.

**Pourquoi le LLM n'est-il utilisé que pour le style ?**
Mesuré : il n'améliore ni la catégorie, ni la couleur, ni la saison ; il aide seulement quand FashionCLIP hésite sur
le style.
