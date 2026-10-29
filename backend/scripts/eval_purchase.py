"""Évalue l'agent Purchase (Qwen2.5-1.5B + LoRA) sur 10 cas hors des 25 trajectoires SFT.

Trois métriques, calculées sur le vrai `run_agent` + `PurchaseToolSandbox` :
- format    : chaque sortie du modèle est un <tool_call> ou un <final> JSON valide,
              et la boucle se termine par un <final>
- outils    : uniquement des noms du sandbox, et inspect_wardrobe en premier
- fidelite  : les montants (X TND) et la médiane cités dans l'explication
              correspondent aux résultats des outils (et au prix du cas)

Compare AVEC LoRA et SANS adapter (`PeftModel.disable_adapter`), sans modifier
purchase_llm.py / purchase_tools.py / purchase_agent.py.

Depuis backend/ :
    python -m scripts.eval_purchase
    python -m scripts.eval_purchase --mode lora
    python -m scripts.eval_purchase --mode base
    python -m scripts.eval_purchase --mode lora --debug
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
import uuid
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.ml import purchase_llm  # noqa: E402
from app.services.catalog_index import CatalogIndex, _load_index  # noqa: E402
from app.services.purchase_tools import TOOL_SPECS, PurchaseToolSandbox  # noqa: E402

SFT_PATH = BACKEND / "app" / "data" / "purchase_llm_sft.jsonl"
ALLOWED_TOOLS = {spec["name"] for spec in TOOL_SPECS}

# Prix / couleurs / tailles de garde-robe absents du jsonl d'entraînement
# (SFT = noir 59 n=0, beige 89 n=8, blanc 75 n=12, rouge 95 n=6 + hors_perimetre).
CASES = [
    {"id": "01", "category": "accessoire", "color": "vert", "price": 42, "wardrobe_size": 3},
    {"id": "02", "category": "haut", "color": "bleu", "price": 120, "wardrobe_size": 4},
    {"id": "03", "category": "bas", "color": "gris", "price": 45, "wardrobe_size": 10},
    {"id": "04", "category": "robe", "color": "rose", "price": 150, "wardrobe_size": 2},
    {"id": "05", "category": "veste", "color": "kaki", "price": 200, "wardrobe_size": 5},
    {"id": "06", "category": "chaussures", "color": "marron", "price": 110, "wardrobe_size": 7},
    {"id": "07", "category": "sac", "color": "doré", "price": 35, "wardrobe_size": 1},
    {"id": "08", "category": "haut", "color": "marine", "price": None, "wardrobe_size": 9},
    {"id": "09", "category": "robe", "color": "olive", "price": 68, "wardrobe_size": 15},
    {"id": "10", "category": "accessoire", "color": "argent", "price": 25, "wardrobe_size": 0},
]

_TND_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*TND", re.I)
_MEDIAN_RE = re.compile(r"m[ée]diane[^\d]{0,24}(\d+(?:[.,]\d+)?)", re.I)
_WARDROBE_MIX = ["haut", "bas", "veste", "chaussures", "sac", "robe"]


def _sft_tasks() -> set[tuple]:
    keys = set()
    for line in SFT_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        for msg in json.loads(line)["messages"]:
            if msg["role"] != "user" or "Analyse cet achat" not in msg["content"]:
                continue
            payload = msg["content"].split("\n", 1)[1]
            task = json.loads(payload)
            keys.add((task.get("category"), task.get("color"), task.get("price"), task.get("wardrobe_size")))
    return keys


def _assert_held_out() -> None:
    trained = _sft_tasks()
    overlap = [
        case for case in CASES
        if (case["category"], case["color"], case["price"], case["wardrobe_size"]) in trained
    ]
    if overlap:
        raise SystemExit(f"Cas de test présents dans le SFT : {overlap}")
    if len(trained) != 25:
        raise SystemExit(f"SFT attendu : 25 trajectoires, trouvé : {len(trained)}")


def _unit(vec) -> np.ndarray:
    vec = np.asarray(vec, dtype=float)
    return vec / max(float(np.linalg.norm(vec)), 1e-12)


def _catalog_by_category(products, vectors) -> dict[str, list[np.ndarray]]:
    cats = products["dressme_category"].to_numpy()
    out: dict[str, list[np.ndarray]] = {}
    for i, cat in enumerate(cats):
        out.setdefault(str(cat), []).append(_unit(vectors[i]))
    return out


def _pick(pool: list[np.ndarray], offset: int) -> np.ndarray:
    if not pool:
        rng = np.random.default_rng(offset + 1)
        return _unit(rng.normal(size=512))
    return pool[offset % len(pool)]


def _owned(by_cat: dict[str, list[np.ndarray]], size: int, seed: int) -> list[tuple]:
    owned = []
    i = 0
    while len(owned) < size:
        cat = _WARDROBE_MIX[i % len(_WARDROBE_MIX)]
        vec = _pick(by_cat.get(cat, []), seed + 10 * i + size)
        item = SimpleNamespace(
            id=uuid.uuid4(),
            image_url=f"eval://{cat}/{i}",
            category=cat,
        )
        owned.append((item, vec))
        i += 1
    return owned


def _task(case: dict) -> dict:
    return {
        "category": case["category"],
        "color": case["color"],
        "price": case["price"],
        "wardrobe_size": case["wardrobe_size"],
    }


class RecordingSandbox:
    """Délègue au vrai sandbox et mémorise nom → résultat (pour la fidélité)."""

    def __init__(self, inner: PurchaseToolSandbox) -> None:
        self.inner = inner
        self.results: dict[str, object] = {}

    def call(self, name: str, **kwargs):
        result = self.inner.call(name, **kwargs)
        self.results[name] = result
        return result


def _format_ok(raws: list[str], finished: bool) -> bool:
    if not raws or not finished:
        return False
    for text in raws:
        tool = purchase_llm._TOOL_RE.search(text or "")
        final = purchase_llm._FINAL_RE.search(text or "")
        if tool:
            try:
                body = json.loads(tool.group(1))
            except json.JSONDecodeError:
                return False
            if not body.get("name"):
                return False
        elif final:
            try:
                body = json.loads(final.group(1))
            except json.JSONDecodeError:
                return False
            if not str(body.get("explanation") or "").strip():
                return False
        else:
            return False
    return True


def _tools_ok(trace: list[str]) -> bool:
    return bool(trace) and trace[0] == "inspect_wardrobe" and all(name in ALLOWED_TOOLS for name in trace)


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _close(mentioned: float, allowed: list[float]) -> bool:
    for value in allowed:
        if abs(mentioned - value) <= 0.05:
            return True
        if abs(mentioned - round(value)) <= 0.05:
            return True
    return False


def _allowed_amounts(task: dict, results: dict) -> list[float]:
    amounts: list[float] = []
    if task.get("price") is not None:
        amounts.append(float(task["price"]))
    insight = results.get("compare_market_price")
    if isinstance(insight, dict):
        for key in ("price", "market_median", "market_min", "market_max"):
            number = _as_float(insight.get(key))
            if number is not None:
                amounts.append(number)
    neighbours = results.get("search_tunisian_catalog") or []
    if isinstance(neighbours, list):
        for row in neighbours:
            number = _as_float(row.get("price") if isinstance(row, dict) else None)
            if number is not None:
                amounts.append(number)
    cost = results.get("estimate_cost_per_wear")
    if isinstance(cost, dict):
        number = _as_float(cost.get("cost_per_wear"))
        if number is not None:
            amounts.append(number)
    return amounts


def _fidelity_ok(explanation: str | None, task: dict, results: dict) -> bool:
    if not explanation:
        return False
    amounts = [_as_float(m) for m in _TND_RE.findall(explanation)]
    medians = [_as_float(m) for m in _MEDIAN_RE.findall(explanation)]
    amounts = [n for n in amounts if n is not None]
    medians = [n for n in medians if n is not None]
    allowed = _allowed_amounts(task, results)
    insight = results.get("compare_market_price") if isinstance(results.get("compare_market_price"), dict) else None
    expected_median = _as_float(insight.get("market_median")) if insight else None

    if not amounts and not medians:
        # Rien à vérifier si les outils n'ont pas donné de prix / médiane.
        return expected_median is None and task.get("price") is None

    if any(not _close(n, allowed) for n in amounts):
        return False
    if expected_median is None:
        return not medians
    if not medians:
        return False
    return all(_close(n, [expected_median]) for n in medians)


def _yes(ok: bool) -> str:
    return "oui" if ok else "non"


def _print_lora_modules(model) -> None:
    print("=== adapter LoRA ===")
    print(f"type              {type(model)}")
    print(f"active_adapters   {getattr(model, 'active_adapters', None)}")
    config = getattr(model, "peft_config", None)
    print(f"peft_config       {config}")
    names = [name for name, _ in model.named_modules() if "lora_" in name]
    print(f"modules LoRA      {len(names)}")
    for name in names:
        print(f"  {name}")
    if not names:
        print("  (aucun module dont le nom contient lora_ — adapter inactif ou non chargé)")


def _compare_prompt_to_sft(tokenizer, eval_messages: list[dict]) -> None:
    """System prompt + chat template vs jsonl SFT et vs notebook (même apply_chat_template)."""
    print("=== comparaison prompt / SFT / notebook ===")
    sft = json.loads(SFT_PATH.read_text(encoding="utf-8").splitlines()[1])
    sft_system = sft["messages"][0]["content"]
    sft_user = sft["messages"][1]["content"]
    user_prefix = "Analyse cet achat. N'invente rien, appelle les outils."
    print(f"system prompt identique au jsonl     {sft_system == purchase_llm.SYSTEM_PROMPT}")
    print(f"préfixe user identique               {sft_user.startswith(user_prefix)}")
    print(f"balises dans le system               {'<tool_call>' in sft_system and '<final>' in sft_system}")
    print(f"tokenizer inférence                  {getattr(tokenizer, 'name_or_path', None)}")
    print("entraînement (notebook + finetune) : AutoTokenizer.from_pretrained(Qwen/Qwen2.5-1.5B-Instruct)")
    print("entraînement : apply_chat_template(messages, tokenize=False)  — PAS add_generation_prompt")
    print("inférence    : apply_chat_template(messages, tokenize=False, add_generation_prompt=True)")
    sft_prefix = sft["messages"][:2]
    trained = tokenizer.apply_chat_template(sft_prefix, tokenize=False, add_generation_prompt=False)
    inferred_sft = tokenizer.apply_chat_template(sft_prefix, tokenize=False, add_generation_prompt=True)
    inferred_eval = tokenizer.apply_chat_template(eval_messages, tokenize=False, add_generation_prompt=True)
    same_body = trained == inferred_sft.removesuffix("<|im_start|>assistant\n")
    print(f"préfixe SFT train == inférence (hors <|im_start|>assistant)  {same_body}")
    print(f"eval cas 02 commence comme SFT (system+user Qwen)            {inferred_eval.startswith(inferred_sft.split('<|im_start|>user')[0])}")
    print("--- template SFT 2 premiers messages, add_generation_prompt=False (comme le notebook) ---")
    print(trained)
    print("--- mêmes 2 messages, add_generation_prompt=True (comme _generate_local) ---")
    print(inferred_sft)


def _make_generate(use_lora: bool, raws: list[str], debug: bool = False):
    """Enregistre le texte brut. LoRA = pipeline existant ; base = disable_adapter()."""
    tokenizer, model = purchase_llm._local_pipeline()
    if debug:
        _print_lora_modules(model)

    def generate(messages: list[dict]) -> str:
        step = len(raws) + 1
        adapter = nullcontext() if use_lora else model.disable_adapter()
        if debug:
            print()
            print(f"======== étape {step} / {purchase_llm.MAX_TOOL_STEPS} ========")
            print("--- messages envoyés (liste Python, avant chat template) ---")
            print(json.dumps(messages, ensure_ascii=False, indent=2))
            try:
                rendered = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True,
                )
            except Exception:
                print("--- exception apply_chat_template ---")
                traceback.print_exc()
                rendered = None
            else:
                print("--- prompt tokenisé (apply_chat_template + add_generation_prompt=True) ---")
                print(rendered)
        try:
            with adapter:
                text = purchase_llm._generate_local(messages)
        except Exception as exc:
            print("--- exception _generate_local ---")
            print(f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
            raws.append("")
            return ""
        raws.append(text)
        if debug:
            print("--- texte BRUT (repr) ---")
            print(repr(text))
            print("--- texte BRUT ---")
            print(text)
            print(f"longueur={len(text)}  parse_action={purchase_llm.parse_action(text)!r}")
        return text

    return generate


def _run_case(case: dict, by_cat: dict, catalog: CatalogIndex, use_lora: bool, debug: bool = False) -> dict:
    task = _task(case)
    owned = _owned(by_cat, case["wardrobe_size"], seed=int(case["id"]) * 17)
    candidate = _pick(by_cat.get(case["category"], []), offset=int(case["id"]) * 31 + 3)
    sandbox = PurchaseToolSandbox(catalog=catalog)
    sandbox.bind(
        embedding=candidate,
        category=case["category"],
        owned=owned,
        price=case["price"],
        item={"category": case["category"], "color": case["color"]},
    )
    recorded = RecordingSandbox(sandbox)
    raws: list[str] = []
    generate = _make_generate(use_lora, raws, debug=debug)
    if debug:
        tokenizer, _model = purchase_llm._local_pipeline()
        preview = [
            {"role": "system", "content": purchase_llm.SYSTEM_PROMPT},
            {"role": "user", "content": "Analyse cet achat. N'invente rien, appelle les outils.\n"
                                        + json.dumps(task, ensure_ascii=False)},
        ]
        _compare_prompt_to_sft(tokenizer, preview)
        print()
        print("=== run_agent cas 02 ===")
        print(f"purchase_llm_enabled  {purchase_llm.get_settings().purchase_llm_enabled}")
        print(f"task                  {json.dumps(task, ensure_ascii=False)}")
    result = purchase_llm.run_agent(task, recorded, generate=generate)
    if debug:
        print()
        print("=== fin run_agent ===")
        print(f"result is None        {result is None}")
        print(f"nb sorties brutes     {len(raws)}")
        print(f"trace outils          {result['tools'] if result else []}")
        if result is None:
            print("trace vide : parse_action a renvoyé None au premier tour (ou <final> sans texte),")
            print("donc run_agent a fait break / return None sans jamais append sur trace.")
    trace = list(result["tools"]) if result else []
    explanation = result["text"] if result else None
    return {
        "id": case["id"],
        "label": f"{case['category']} {case['color']} {case['price'] if case['price'] is not None else 'NA'} n={case['wardrobe_size']}",
        "mode": "lora" if use_lora else "base",
        "format": _format_ok(raws, finished=result is not None),
        "outils": _tools_ok(trace),
        "fidelite": _fidelity_ok(explanation, task, recorded.results),
        "trace": " > ".join(trace) if trace else "—",
        "explication": (explanation or "").replace("\n", " ").strip()[:80],
    }


def _print_table(rows: list[dict]) -> None:
    header = f"{'cas':<36} {'mode':<6} {'format':<8} {'outils':<8} {'fidelite':<8} trace"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['id']} {row['label']:<33} {row['mode']:<6} "
            f"{_yes(row['format']):<8} {_yes(row['outils']):<8} {_yes(row['fidelite']):<8} "
            f"{row['trace']}"
        )
    print("-" * len(header))
    for mode in ("lora", "base"):
        subset = [row for row in rows if row["mode"] == mode]
        if not subset:
            continue
        n = len(subset)
        fmt = 100 * sum(row["format"] for row in subset) / n
        tools = 100 * sum(row["outils"] for row in subset) / n
        fid = 100 * sum(row["fidelite"] for row in subset) / n
        print(f"{'MOYENNE ' + mode:<36} {mode:<6} {fmt:5.0f} %   {tools:5.0f} %   {fid:5.0f} %")


def main() -> int:
    parser = argparse.ArgumentParser(description="Évalue Purchase LLM (LoRA vs base) sur 10 cas hors SFT.")
    parser.add_argument("--mode", choices=("both", "lora", "base"), default="both")
    parser.add_argument("--debug", action="store_true",
                        help="Un seul cas (02), dump prompt + brut + exceptions + modules LoRA.")
    parser.add_argument("--from-id", default="01", help="Reprend à partir de cet id (ex. 06).")
    args = parser.parse_args()

    if not purchase_llm._adapter_ready():
        print("Adapter LoRA introuvable. Attendu :")
        print(f"  {purchase_llm.ADAPTER_DIR / 'adapter_config.json'}")
        print(f"  {purchase_llm.ADAPTER_DIR / 'adapter_model.safetensors'}")
        return 1
    _assert_held_out()

    products, vectors = _load_index()
    if len(products) == 0:
        print("Index catalogue manquant — lance `python -m scripts.build_catalog_index`.")
        return 1

    catalog = CatalogIndex()
    by_cat = _catalog_by_category(products, vectors)

    print(f"base     {purchase_llm.BASE_MODEL_ID}")
    print(f"adapter  {purchase_llm.ADAPTER_DIR}")
    print(f"cas      {len(CASES)} hors des {len(_sft_tasks())} trajectoires SFT")
    print(f"catalogue {len(products)} embeddings")
    print()

    if args.debug:
        mode = "lora" if args.mode == "both" else args.mode
        case = next(c for c in CASES if c["id"] == "02")
        print(f"DEBUG  cas 02 uniquement, mode={mode}")
        print()
        row = _run_case(case, by_cat, catalog, use_lora=(mode == "lora"), debug=True)
        print()
        _print_table([row])
        return 0
    modes = {"both": (True, False), "lora": (True,), "base": (False,)}[args.mode]
    start = next(i for i, case in enumerate(CASES) if case["id"] == args.from_id)
    selected = CASES[start:]

    rows = []
    for use_lora in modes:
        for case in selected:
            try:
                row = _run_case(case, by_cat, catalog, use_lora=use_lora)
            except Exception:
                traceback.print_exc()
                row = {
                    "id": case["id"],
                    "label": f"{case['category']} {case['color']} {case['price'] if case['price'] is not None else 'NA'} n={case['wardrobe_size']}",
                    "mode": "lora" if use_lora else "base",
                    "format": False, "outils": False, "fidelite": False,
                    "trace": "erreur", "explication": "",
                }
            rows.append(row)
            line = (f"[{row['mode']}] {row['id']} {row['label']}  "
                    f"format={_yes(row['format'])} outils={_yes(row['outils'])} "
                    f"fidelite={_yes(row['fidelite'])}  trace={row['trace']}")
            print(line, flush=True)
            (BACKEND / "scripts" / ".eval_purchase_partial.log").open("a", encoding="utf-8").write(line + "\n")
    print()
    _print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
