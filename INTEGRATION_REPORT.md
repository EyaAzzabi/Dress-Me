# Intégration LLMAgent — état final du 15 octobre 2026

## Mise à jour du 21 octobre : cohérence des associations

La conversation distingue désormais une base haut + bas d'une robe/combinaison.
Chaque piste structurée est contrôlée : robe + bas, deux bas ou deux robes sont
refusés. Les compléments optionnels mentionnant ces catégories sont également
contrôlés, sans confondre une veste en jean avec un jean. Deux pistes alternatives
peuvent naturellement utiliser des bases différentes. Les catégories usuelles
françaises et anglaises sont prises en compte.

Le modèle reçoit des consignes de construction de tenue et doit séparer ses
alternatives. Une réponse incompatible déclenche la correction bornée existante ;
si elle reste invalide, elle n'est pas affichée. La version du cache de conversation
change pour ne pas réutiliser les anciennes suggestions. Les contrôles portent sur
les catégories déclarées et les références structurées : ils ne prouvent ni la
bonne classification d'une photo ni la cohérence de toute phrase libre possible.
Les modèles, le frontend et les algorithmes/scores des autres agents sont conservés.

Vérification backend : **273 tests réussis, 13 ignorés**, dont 21 nouveaux cas de
cohérence et de réparation, avec fournisseur simulé dans les tests automatisés.
Deux appels **réels à Groq GPT-OSS 120B**, sur un dressing synthétique sans lecture
ni écriture en base, ont produit des tenues distinctes : robe + veste + chaussures,
et haut + bas + veste + chaussures. Durées : 2,69 s et 1,87 s. La troisième relance
a rencontré une limitation de quota ; elle n'est pas comptée comme un succès.
Le rapport brut reste local : `verification/outfit-coherence-live-20261021.json`.

## État de l'intégration initiale

### Réponses d'avis directes, 21 octobre

Les demandes d'avis appellent maintenant une réponse brève et explicite, avec
une justification liée aux informations disponibles. Le modèle distingue en
interne avis, conseil et clarification ; ce champ n'est pas affiché dans l'API.
Pour un avis, le serveur retire les pistes de tenue et les relances non demandées.
Les questions restent libres : aucune banque de réponses oui/non n'est utilisée.
La pièce sélectionnée est prioritaire pour résoudre « elle » dans la conversation.

Essais réels Groq sur données synthétiques : « elle est moche ? » a reçu
« Non, elle n'est pas moche… » ; « Le noir et le bleu, ça va ensemble ? » a reçu
« Oui… ». Les modèles 120B et de secours 20B ont été utilisés. Un essai a aussi
révélé une affirmation inventée sur le rendu porté ; un contrôle ciblé et ses
tests de régression ont été ajoutés pour refuser ces affirmations et demander une
correction. Ce contrôle ciblé ne constitue pas une preuve de toute la prose.
Rapport fournisseur local : `verification/direct-opinions-live-20261021.json`.

Suite backend finale après ces changements : **280 tests réussis, 13 ignorés**,
10 avertissements, 15,19 s. Les tests automatisés utilisent des fournisseurs simulés.

Avant publication, le 22 octobre : les **121 tests ciblés LLMAgent, conversation et
routes de chat réussissent** en 3,19 s. La relance de la suite complète reste sans
progression après 26 tests, à l'entrée du test du modèle de compatibilité réel ;
elle a été interrompue sans modifier cet agent. Les 280 réussites ci-dessus
correspondent à l'exécution complète du 21 octobre, pas à cette relance.

Le backend DressMe a été relancé sur `8001`, le frontend sur `5174`, afin de
laisser Pulse AI fonctionner sur ses ports `8000` et `5173`.

Branche de publication : `sarah/llm-agent`, issue du commit
`94d6b10005050726f14370f0661189961b0ff1e6`. Intégration préparée sur
`sarah/llm-agent-integration`, puis transférée sur la branche de contribution.
Le fichier initial non suivi `backend/test_mistral_local.py` est conservé intact.
Les documents README_LLM_AGENT.md et IMPLEMENTATION_REPORT.md de référence ont été
lus. Les fichiers LLM ciblés ont été comparés au même commit de base, puis intégrés
sélectivement ; aucun backend complet ni frontend de référence n'a été substitué.

## Résultat dans le frontend commun

Le menu **Assistant IA** ouvre une conversation : saisie libre d'une question,
questions de suivi avec historique utilisateur et assistant, sélection d'une pièce, d'une tenue ou d'une analyse d'achat
enregistrée. Les exemples fictifs et leur route `/llm/preview` ont été retirés.
La conversation utilise les données du compte connecté et peut proposer des conseils
généraux même si le dressing est vide, sans inventer de vêtements possédés.
Elle rédige désormais ses réponses et propose des pistes de style, plutôt que de
choisir des phrases prédéfinies. Une pièce sélectionnée conserve l'accès aux autres
pièces du dressing pour permettre des associations. Les références des pièces
utilisées sont vérifiées ; les compléments suggérés sont séparés et optionnels.
La case « Utiliser uniquement les pièces de mon dressing » interdit ces compléments
dans les pistes structurées. Les huit derniers messages sont transmis au modèle,
avec leurs rôles ; ils ne constituent pas des preuves de propriété de vêtements.
Les sources sont consultables sous chaque réponse. Les messages restent dans la
mémoire de la page et ne sont pas enregistrés dans une nouvelle table.

Les styles, la navigation, les écrans et les assets du frontend commun sont
conservés ; seules la conversation et l'indication des étapes d'ajout photo sont
ajoutées. Les composants existants continuent d'afficher les narrations de profil
et les explications de tenue/achat.

L'avertissement « Le premier ajout peut être plus long » apparaît seulement lors
de la première analyse photo de la session du navigateur, y compris après un
rechargement de page. Les ajouts suivants gardent uniquement le message de progression.

Groq est conservé, avec **`openai/gpt-oss-120b` pour la conversation**
(`LLM_CHAT_MODEL`) et `openai/gpt-oss-20b` pour les narrations enregistrées.
Le 20B est aussi configuré comme secours génératif en cas de quota du 120B
(`LLM_CHAT_FALLBACK_MODEL`), avec le même contrôle des références et du format.
La bascule est limitée au cas quota ; une erreur d'authentification n'entraîne pas
un nouvel essai avec une autre variante de modèle. Le secours ne revient pas au
catalogue de phrases de l'ancien assistant.
Le 120B a été testé réellement et sa prise en charge du JSON Schema est documentée
par [Groq](https://console.groq.com/docs/model/openai/gpt-oss-120b).
Le modèle local Llama n'a pas été téléchargé pour le texte. Cette décision ne
change pas FashionCLIP. Le choix est fondé sur les essais disponibles, pas sur un
benchmark exhaustif des modèles.

## Fichiers d'implémentation modifiés ou ajoutés

| Fichier | Rôle |
| --- | --- |
| `backend/app/agents/llm_agent.py` | Fournisseurs, délais, reprises, cache, rendu validé et sélection des faits selon la question. |
| `backend/app/services/llm_narratives.py` | Plans français contraints pour les narrations enregistrées profil/tenue/achat. |
| `backend/app/services/llm_conversation.py` | Génération de conseils, historique complet, références validées, compléments optionnels et contrôles ciblés des types de vêtements non confirmés. |
| `backend/app/agents/style_profile_agent.py` | Profil français, cache par utilisateur et accès aux faits sans narration. |
| `backend/app/agents/orchestrator.py` | Explications des décisions existantes, actualisation des champs des tenues réutilisées. |
| `backend/app/core/config.py` | Limites LLM validées et clé masquée dans la représentation. |
| `backend/app/api/routes/llm.py` | GET `/llm/context` et POST `/llm/chat`, authentifiés, avec contrôle propriétaire et sans écritures en base. |
| `backend/app/api/routes/__init__.py` | Enregistrement de la route LLM. |
| `backend/.env.example` | Paramètres LLM sans secrets. |
| `backend/requirements-llm-test.txt` | Environnement optionnel des tests LLM seuls. |
| `backend/scripts/smoke_llm.py` | Appel fournisseur explicite sur faits synthétiques. |
| `backend/scripts/run_local.py` | Lancement avec priorité au `.env` du dépôt sur les anciennes variables héritées. |
| `backend/tests/test_llm_agent.py` | Fournisseurs, cache, erreurs et HTTP local. |
| `backend/tests/test_llm_narratives.py` | Faits, validation, conversation ciblée et préservation des verdicts. |
| `backend/tests/test_llm_integrations.py` | Orchestrateur, SQLite, API, scores et historique avec I/O externes simulées. |
| `backend/tests/test_llm_chat_route.py` | Isolation des comptes, données réelles, absence de modification des décisions et cas vides/erreurs. |
| `backend/tests/test_llm_conversation.py` | Prose générée, mémoire, références inconnues, mode dressing seulement, nettoyage des références internes et correction bornée. |
| `backend/tests/test_tryon_agent.py` | Isolation des réglages de test uniquement. |
| `frontend/web/src/LlmAssistant.tsx` | Conversation, contexte personnel, sources, états vides et erreurs. |
| `frontend/web/src/App.tsx` | Navigation et progression envoi/analyse photo. |
| `frontend/web/src/styles.css` | Styles de la conversation dans la charte existante, desktop et mobile. |

Les agents RecommendationAgent, PurchaseAgent, ContextAgent, VisionAgent,
les modèles ML, migrations, schémas métier et `backend/requirements.txt` sont
inchangés. Aucun algorithme de sélection, classement, score ou verdict n'est remplacé.
La conversation lit les tenues et résultats d'achat existants ; elle ne les recalcule
pas et ne les réécrit pas.

## Configuration et préservation des données

Le `.env` local utilise les réglages Groq de la référence, avec une base SQLite
isolée sous `.venv/integration-verification` et le stockage photo explicite dans
`backend/uploads`. Les configurations précédentes sont sauvegardées sous `.venv`.
Le fichier `.env` de référence reste intact. Les `.env`, clés, jeton navigateur,
photos et bases locales ne sont pas versionnés ; aucune base n'a été supprimée.
La base source de la contribution n'a pas été modifiée.

Les dépendances Windows/Python 3.13.5 de la référence sont réutilisées, ainsi que le
lockfile npm existant. Les modifications de l'utilisatrice pendant la session sont
conservées ; aucune remise à zéro de la base de travail n'est effectuée.

Pour le développement : depuis `backend/`, exécuter avec le Python de référence
`python -m scripts.run_local`. Le backend tourne sur `127.0.0.1:8000`, le frontend
Vite sur `localhost:5173`. Le lanceur local de vérification `run_reference_backend.py`
crée une nouvelle copie de démonstration ; il ne doit pas servir au lancement
quotidien du dressing courant.

## Vérifications réellement obtenues

| Vérification | Résultat |
| --- | --- |
| Suite backend finale, `pytest tests -q -ra --tb=short`, dossier temporaire unique sous `.venv` | **252 réussis, 13 ignorés, 0 échec**, 10 avertissements, 9,68 s. Rapport `verification/generative-tests.xml`. |
| TypeScript, `tsc --noEmit` | Réussi. |
| Build Vite de la conversation | Réussi, 88 modules. |
| Vérification avant publication | Suite relancée : **252 réussis, 13 ignorés**, 9,45 s ; TypeScript et build Vite réussis. |
| Avertissement du premier ajout photo | Navigateur avec API simulée : présent au premier ajout, absent au deuxième et après rechargement ; aucune erreur JavaScript. Aucune insertion en base. |
| Conversation générative navigateur sans interception, avec Groq 120B réel | « Comment styler cette pièce ? » : **2,88 s**, 3 pistes ; relance « le soir, sans talons, uniquement avec mes pièces » : **2,59 s**, 2 pistes sans compléments externes ; entretien avec matière inconnue : **1,59 s**. Résultats dans `verification/generative-ui-results.json`. |
| Modèle de secours 20B, appel réel sur faits synthétiques | Réponse générée valide, 2 idées. Activation de la bascule sur HTTP 429 vérifiée séparément avec fournisseur simulé dans les tests de route. |
| Desktop et mobile 390 px | Captures inspectées, aucun débordement horizontal ni erreur JavaScript. |
| Upload authentifié puis lecture `/media/` | HTTP 200, octets identiques. Upload JPEG mesuré à **0,019 s**. |
| Inférence FashionCLIP sur le JPEG déjà envoyé, sans insertion en base | **9,04 s au premier chargement**, puis **0,05 s à chaud** pour cette image dans le même processus. |
| Comparaison des agents de décision, artefacts ML et migrations | Aucun changement. |
| `git diff --check` et recherche des valeurs réelles des secrets/jeton dans les livrables texte | Réussis. |

Les 13 tests ignorés nécessitent PostgreSQL (12) ou les images brutes FashionCLIP (1).
Les tests unitaires et d'intégration simulent leurs fournisseurs externes ; ils ne
sont pas présentés comme des appels Groq réels. Les appels de conversation ci-dessus
sont, eux, réels, sur les données du compte de démonstration présent en base.
Les anciens résultats `*-simulated` et les captures des premiers essais restent
identifiés comme simulations historiques ; la page active n'utilise plus ces exemples.

Les tests de conversation sur tenues/achats sauvegardés utilisent SQLite réel avec
le fournisseur simulé pour vérifier l'intégrité des décisions et l'isolation des
comptes. Le compte de démonstration utilisé pour le navigateur n'a pas de tenue
générée ; aucune tenue fictive n'a été ajoutée pour masquer cet état.

## Modèle photo et limites

Les poids FashionCLIP manquaient dans le cache de la machine. Le téléchargement
des fichiers requis, dont environ **577 Mo** de poids, est terminé. PyTorch utilise
le CPU (`2.14.1+cpu`, CUDA indisponible), Transformers `5.20.0`. Le même clone Git
ne fournit pas le cache des modèles ni un environnement matériel identique.
L'environnement de la collègue n'a pas été inspecté. Les mesures d'inférence
ci-dessus concernent une image et le processus de mesure, pas la durée complète
garantie de tout futur ajout HTTP. Aucun résultat n'a été falsifié pour accélérer
l'analyse.

Les narrations sauvegardées gardent le planificateur contraint de référence.
La conversation, à la demande explicite de l'utilisatrice, utilise désormais de la
prose rédigée par le modèle. Le schéma, les références des pièces, l'absence de
compléments structurés en mode dressing seulement et certaines confusions de
type (« bas » transformé en « pantalon » sans confirmation) sont contrôlés côté
Python. Les types non confirmés dans les formulations de possession sont ramenés
à la catégorie générique connue, tout en respectant les précisions de l'utilisateur.
Une correction du modèle est possible dans le budget de deux tentatives du modèle
principal. En cas de quota, le secours dispose d'une seule tentative, avec validation
locale ; si lui aussi échoue, aucun faux conseil n'est affiché.
Les scores et verdicts enregistrés sont lus sans modification et affichés dans un
bloc séparé provenant du serveur, indépendant de la prose du modèle.

Cette validation ne prouve pas la vérité de chaque phrase de prose ni la qualité
de chaque conseil. Une réponse de conversation peut encore contenir une erreur ou
une suggestion discutable ; les garanties du rendu strict des narrations ne doivent
pas être attribuées à la prose générative. L'assistant ne voit pas les images, ne
consulte pas le web ni la météo et ne remplace pas le classement algorithmique.

Les captures, rapports bruts et scripts du dossier `verification/` restent locaux ;
ils ne font pas partie du commit de contribution. Les tests automatisés backend,
les scripts `backend/scripts/` et le présent compte rendu sont inclus.

Preuves locales principales : `verification/generative-ui-results.json`,
`verification/assistant-generative-styling.png`,
`verification/assistant-generative-memory.png`,
`verification/assistant-generative-mobile.png`,
`verification/photo-warmup-results.json`. Reproduction du navigateur :
`python verification/check_generative_assistant.py`, avec Playwright/Chromium déjà présents.
`verification/generative-evaluation.json` est un essai fournisseur sur faits
synthétiques : les appels 120B et leur relance ont réussi, tandis que le 20B a
retourné HTTP 400 pour ce nouveau format dans cet essai. Ce n'est pas un benchmark
comparatif de qualité à conditions égales. Le mode conversation 20B utilise désormais
le mode JSON objet et la validation locale : son essai réel réussi figure dans
`verification/generative-fallback-results.json`. Des essais rapprochés du 120B ont
effectivement rencontré HTTP 429 avant la mise en place du secours et de son
message d'erreur spécifique. Aucun quota ni droit d'accès supplémentaire n'a été acheté.
