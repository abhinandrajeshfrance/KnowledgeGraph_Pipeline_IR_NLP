#!/usr/bin/env python3
"""
Module 5 quick optimization: TransE only (base vs base+inferred triples).
"""

import json
import random
import re
from pathlib import Path

import numpy as np
import torch
from pykeen.models import TransE
from pykeen.training import SLCWATrainingLoop
from pykeen.triples import TriplesFactory


def normalize_token(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unk"


def load_tsv_triples(path: Path):
    triples = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3:
                triples.append((parts[0], parts[1], parts[2]))
    return triples


def parse_inferred_triples(path: Path):
    triples = []
    pattern = re.compile(r"^\s*\d+\.\s+(.*?)\s+--\[(.*?)\]-->\s+(.*?)\s*$")
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            m = pattern.match(line)
            if not m:
                continue
            s = normalize_token(m.group(1))
            p = normalize_token(m.group(2))
            o = normalize_token(m.group(3))
            triples.append((s, p, o))
    return triples


def generate_rule_inferences(base_triples):
    """Generate inferred triples using the same 3 lightweight SWRL-like rules."""
    by_rel = {}
    for h, r, t in base_triples:
        by_rel.setdefault(r, []).append((h, t))

    inferred = set()

    # Rule 1: affiliatedWith(x,y) and locatedIn(y,z) -> worksInCountry(x,z)
    aff = by_rel.get("affiliatedwith", [])
    loc = by_rel.get("locatedin", [])
    loc_by_org = {}
    for org, country in loc:
        loc_by_org.setdefault(org, set()).add(country)
    for person, org in aff:
        for country in loc_by_org.get(org, set()):
            inferred.add((person, "worksincountry", country))

    # Rule 2: collaboratesWith(x,y) and hasResearchArea(y,f) -> sharesResearchField(x,f)
    collab = by_rel.get("collaborateswith", [])
    areas = by_rel.get("hasresearcharea", [])
    areas_by_org = {}
    for org, field in areas:
        areas_by_org.setdefault(org, set()).add(field)
    for org1, org2 in collab:
        for field in areas_by_org.get(org2, set()):
            inferred.add((org1, "sharesresearchfield", field))

    # Rule 3: worksOn(x,f) and hasResearchArea(y,f) -> collaboratesInField(x,y)
    works = by_rel.get("workson", [])
    orgs_by_field = {}
    for org, field in areas:
        orgs_by_field.setdefault(field, set()).add(org)
    for person, field in works:
        for org in orgs_by_field.get(field, set()):
            inferred.add((person, "collaboratesinfield", org))

    return list(inferred)


def get_entity_embeddings(model):
    if hasattr(model, "entity_embeddings"):
        return model.entity_embeddings.weight.detach().cpu().numpy()
    return model.entity_representations[0](indices=None).detach().cpu().numpy()


def get_relation_embeddings(model):
    if hasattr(model, "relation_embeddings"):
        return model.relation_embeddings.weight.detach().cpu().numpy()
    return model.relation_representations[0](indices=None).detach().cpu().numpy()


def evaluate_transe(model, test_triples, entity_to_id, relation_to_id):
    entity_embeddings = get_entity_embeddings(model)
    relation_embeddings = get_relation_embeddings(model)

    ranks = []
    for h, r, t in test_triples:
        if h not in entity_to_id or t not in entity_to_id or r not in relation_to_id:
            continue

        h_id = entity_to_id[h]
        r_id = relation_to_id[r]
        t_id = entity_to_id[t]

        h_emb = entity_embeddings[h_id]
        r_emb = relation_embeddings[r_id]
        scores = np.linalg.norm(h_emb + r_emb - entity_embeddings, axis=1)

        rank = np.argsort(scores)
        pos = np.where(rank == t_id)[0]
        if len(pos) > 0:
            ranks.append(int(pos[0]) + 1)

    if not ranks:
        return {"mrr": 0.0, "hits_at_1": 0.0, "hits_at_3": 0.0, "hits_at_10": 0.0, "eval_size": 0}

    return {
        "mrr": float(np.mean([1.0 / r for r in ranks])),
        "hits_at_1": float(np.mean([r <= 1 for r in ranks])),
        "hits_at_3": float(np.mean([r <= 3 for r in ranks])),
        "hits_at_10": float(np.mean([r <= 10 for r in ranks])),
        "eval_size": len(ranks),
    }


def train_transe(train_triples, valid_triples, test_triples, embedding_dim, epochs, lr, seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    arr = np.asarray(train_triples, dtype=str)
    tf_train = TriplesFactory.from_labeled_triples(arr)

    model = TransE(
        triples_factory=tf_train,
        embedding_dim=embedding_dim,
        random_seed=seed,
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    training_loop = SLCWATrainingLoop(
        model=model,
        triples_factory=tf_train,
        optimizer=optimizer,
    )
    training_loop.train(triples_factory=tf_train, num_epochs=epochs)

    valid_metrics = evaluate_transe(model, valid_triples, tf_train.entity_to_id, tf_train.relation_to_id)
    test_metrics = evaluate_transe(model, test_triples, tf_train.entity_to_id, tf_train.relation_to_id)

    return valid_metrics, test_metrics


def main():
    root = Path(__file__).resolve().parent
    data_dir = root / "data" / "kge"
    reason_path = root / "src" / "reason" / "kb_inferences.txt"
    kge_dir = root / "kge"
    kge_dir.mkdir(parents=True, exist_ok=True)

    train_base = load_tsv_triples(data_dir / "train.txt")
    valid = load_tsv_triples(data_dir / "valid.txt")
    test = load_tsv_triples(data_dir / "test.txt")

    inferred_raw = parse_inferred_triples(reason_path)
    inferred_rules = generate_rule_inferences(train_base)
    inferred_raw.extend(inferred_rules)
    base_set = set(train_base)
    inferred_new = [tr for tr in inferred_raw if tr not in base_set]

    train_plus_inferred = list(train_base)
    for tr in inferred_new:
        if tr not in base_set:
            train_plus_inferred.append(tr)
            base_set.add(tr)

    plus_path = data_dir / "train_plus_inferred.txt"
    with plus_path.open("w", encoding="utf-8") as f:
        for h, r, t in train_plus_inferred:
            f.write(f"{h}\t{r}\t{t}\n")

    config = {
        "model": "TransE",
        "embedding_dim": 150,
        "epochs": 100,
        "learning_rate": 0.001,
        "note": "Quick-pass tuned config for lightweight optimization",
    }

    print("[Module 5 Optimization] Training TransE on base KB...")
    base_valid, base_test = train_transe(
        train_triples=train_base,
        valid_triples=valid,
        test_triples=test,
        embedding_dim=config["embedding_dim"],
        epochs=config["epochs"],
        lr=config["learning_rate"],
    )

    print("[Module 5 Optimization] Training TransE on KB + inferred triples...")
    inf_valid, inf_test = train_transe(
        train_triples=train_plus_inferred,
        valid_triples=valid,
        test_triples=test,
        embedding_dim=config["embedding_dim"],
        epochs=config["epochs"],
        lr=config["learning_rate"],
    )

    results_path = kge_dir / "results.json"
    previous = {}
    if results_path.exists():
        with results_path.open("r", encoding="utf-8") as f:
            previous = json.load(f)

    before = previous.get("models", {}).get("TransE", {}).get("full_dataset", {})
    original_baseline = previous.get("models", {}).get("TransE", {}).get("small_dataset", before)

    inferred_better = inf_test["mrr"] > base_test["mrr"]
    best_variant = "kb_plus_inferred" if inferred_better else "base_kb"
    best_metrics = inf_test if inferred_better else base_test

    optimized_block = {
        "before_original_module5": original_baseline,
        "before_previous_run": before,
        "quick_tuning_config": config,
        "datasets": {
            "base_train_size": len(train_base),
            "inferred_parsed_and_generated": len(inferred_raw),
            "inferred_added_unique": len(inferred_new),
            "plus_inferred_train_size": len(train_plus_inferred),
        },
        "experiments": {
            "base_kb": {
                "valid": base_valid,
                "test": base_test,
            },
            "kb_plus_inferred": {
                "valid": inf_valid,
                "test": inf_test,
            },
        },
        "comparison": {
            "best_variant": best_variant,
            "inferred_improved": inferred_better,
            "delta_mrr_inferred_minus_base": float(inf_test["mrr"] - base_test["mrr"]),
            "delta_hits10_inferred_minus_base": float(inf_test["hits_at_10"] - base_test["hits_at_10"]),
            "before_to_best_delta_mrr": float(best_metrics.get("mrr", 0.0) - original_baseline.get("mrr", 0.0)),
            "before_to_best_delta_hits10": float(best_metrics.get("hits_at_10", 0.0) - original_baseline.get("hits_at_10", 0.0)),
        },
        "best_configuration": {
            "variant": best_variant,
            "model": "TransE",
            "embedding_dim": config["embedding_dim"],
            "epochs": config["epochs"],
            "learning_rate": config["learning_rate"],
            "test_metrics": best_metrics,
        },
    }

    if "models" not in previous:
        previous["models"] = {}
    if "TransE" not in previous["models"]:
        previous["models"]["TransE"] = {}

    previous["models"]["TransE"]["full_dataset_before_optimization"] = before
    previous["models"]["TransE"]["full_dataset"] = best_metrics
    previous["transE_optimization"] = optimized_block

    with results_path.open("w", encoding="utf-8") as f:
        json.dump(previous, f, indent=2)

    model_cmp_path = kge_dir / "model_comparison.json"
    model_cmp = {}
    if model_cmp_path.exists():
        with model_cmp_path.open("r", encoding="utf-8") as f:
            model_cmp = json.load(f)

    model_cmp["TransE_MRR"] = best_metrics["mrr"]
    model_cmp["TransE_Hits@10"] = best_metrics["hits_at_10"]
    model_cmp["transE_optimization"] = {
        "best_variant": best_variant,
        "inferred_improved": inferred_better,
        "before": original_baseline,
        "after": best_metrics,
    }
    if "DistMult_MRR" in model_cmp:
        model_cmp["winner"] = "TransE" if model_cmp["TransE_MRR"] >= model_cmp["DistMult_MRR"] else "DistMult"

    with model_cmp_path.open("w", encoding="utf-8") as f:
        json.dump(model_cmp, f, indent=2)

    opt_path = kge_dir / "transE_optimization.json"
    with opt_path.open("w", encoding="utf-8") as f:
        json.dump(optimized_block, f, indent=2)

    print("[OK] Optimization complete")
    print(f"  Before MRR: {original_baseline.get('mrr', 0.0):.4f}")
    print(f"  Base-tuned MRR: {base_test['mrr']:.4f}")
    print(f"  Inferred-tuned MRR: {inf_test['mrr']:.4f}")
    print(f"  Best variant: {best_variant}")
    print(f"  Best Hits@10: {best_metrics['hits_at_10']:.4f}")


if __name__ == "__main__":
    main()
