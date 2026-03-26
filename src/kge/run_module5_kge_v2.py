#!/usr/bin/env python3
"""
Module 5: Knowledge Graph Embeddings (KGE) - Simplified Version
- Data preparation
- Model training (TransE, DistMult)
- Evaluation
"""

import json
import random
from pathlib import Path
from collections import defaultdict
import numpy as np
from rdflib import Graph as RDFGraph, Namespace, RDFS

# PyKEEN imports  
from pykeen.datasets import PathDataset
from pykeen.models import TransE, DistMult
from pykeen.training import SLCWATrainingLoop
from pykeen.evaluators import RankBasedEvaluator
import torch

torch.manual_seed(42)
np.random.seed(42)
random.seed(42)

print("[Module 5] Starting Knowledge Graph Embeddings Pipeline (Simplified)...")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "kge"
KGE_DIR = ROOT / "kge"
KGE_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# PART 1: DATA PREPARATION (already done, just verify)
# ============================================================================

print("\n" + "="*80)
print("PART 1: DATA PREPARATION VERIFICATION")
print("="*80)

KB_FILE = ROOT / "kg_artifacts" / "expanded_full_v2.ttl"
print(f"\n[Part 1] Loading knowledge graph from {KB_FILE.name}...")

kb_graph = RDFGraph()
with open(KB_FILE, 'r', encoding='utf-8') as f:
    kb_graph.parse(file=f, format="turtle")

print(f"[Part 1] Loaded knowledge graph with {len(kb_graph)} triples")

# Create entity-to-label mapping
entity_labels = {}
RDFS_ = Namespace("http://www.w3.org/2000/01/rdf-schema#")

def get_entity_label(uri):
    """Extract short label from URI"""
    if str(uri) in entity_labels:
        return entity_labels[str(uri)]
    
    label = kb_graph.value(uri, RDFS.label)
    if label:
        short_label = str(label).lower().replace(" ", "_").replace("/", "_").replace(":", "_")
    else:
        uri_str = str(uri)
        if "#" in uri_str:
            short_label = uri_str.split("#")[-1].lower()
        elif "/" in uri_str:
            short_label = uri_str.split("/")[-1].lower()
        else:
            short_label = uri_str.lower()
    
    short_label = "".join(c if c.isalnum() or c == "_" else "_" for c in short_label)
    short_label = short_label.strip("_")[: 100]
    entity_labels[str(uri)] = short_label
    return short_label

# Extract and normalize triples
triples_raw = [(s, p, o) for s, p, o in kb_graph]
triples_normalized = []
relation_counts = defaultdict(int)

for s, p, o in triples_raw:
    head = get_entity_label(s)
    relation = get_entity_label(p)
    tail = get_entity_label(o)
    
    if head and relation and tail:
        triples_normalized.append((head, relation, tail))
        relation_counts[relation] += 1

triples_unique = list(set(triples_normalized))
print(f"[Part 1] Extracted {len(triples_unique)} unique triples")

# ============================================================================
# PART 2: LOAD DATASETS
# ============================================================================

print("\n" + "="*80)
print("PART 2: LOADING DATASETS")
print("="*80)

print(f"\n[Part 2] Loading dataset from files...")

# Load full dataset
dataset_full = PathDataset(
    training=DATA_DIR / "train.txt",
    validation=DATA_DIR / "valid.txt",
    testing=DATA_DIR / "test.txt",
)

print(f"  Train: {len(dataset_full.training)} triples")
print(f"  Valid: {len(dataset_full.validation)} triples")
print(f"  Test: {len(dataset_full.testing)} triples")
print(f"  Entities: {dataset_full.num_entities}")
print(f"  Relations: {dataset_full.num_relations}")

# Load small dataset
dataset_small = PathDataset(
    training=DATA_DIR / "train_small.txt",
    validation=DATA_DIR / "valid_small.txt",
    testing=DATA_DIR / "test_small.txt",
)

print(f"\n  Small dataset:")
print(f"    Train: {len(dataset_small.training)}")
print(f"    Valid: {len(dataset_small.validation)}")
print(f"    Test: {len(dataset_small.testing)}")

# ============================================================================
# PART 3: MODEL TRAINING - TransE (Full)
# ============================================================================

print("\n" + "="*80)
print("PART 3: MODEL TRAINING - TransE (Full Dataset)")
print("="*80)

print(f"\n[Part 3] Training TransE on full dataset...")
print(f"  - Embedding dimension: 100")
print(f"  - Epochs: 50")
print(f"  - Learning rate: 0.001")
print(f"  - Batch size: 128")

model_transe_full = TransE(
    triples_factory=dataset_full.training,
    embedding_dim=100,
)

training_loop_transe_full = SLCWATrainingLoop(
    model=model_transe_full,
    triples_factory=dataset_full.training,
    learning_rate=0.001,
    batch_size=128,
)

print(f"\n  Training...")
losses = []
for epoch in range(50):
    loss = training_loop_transe_full.train(num_epochs=1)
    losses.append(loss)
    if (epoch + 1) % 10 == 0:
        print(f"    Epoch {epoch + 1}: Loss = {loss:.4f}")

print(f"\n  Evaluating...")
evaluator_transe_full = RankBasedEvaluator()
metric_results_transe_full = evaluator_transe_full.evaluate(
    model=model_transe_full,
    mapped_triples=dataset_full.testing,
    batch_size=128,
    additional_filter_triples=[dataset_full.training.mapped_triples, dataset_full.validation.mapped_triples],
)

print(f"\n[Part 3] TransE Results (Full Dataset):")
print(f"  MRR: {metric_results_transe_full.mean_reciprocal_rank:.4f}")
print(f"  Hits@1: {metric_results_transe_full.hits_at_1:.4f}")
print(f"  Hits@3: {metric_results_transe_full.hits_at_3:.4f}")
print(f"  Hits@10: {metric_results_transe_full.hits_at_10:.4f}")

# ============================================================================
# PART 4: MODEL TRAINING - DistMult (Full)
# ============================================================================

print("\n" + "="*80)
print("PART 4: MODEL TRAINING - DistMult (Full Dataset)")
print("="*80)

print(f"\n[Part 4] Training DistMult on full dataset...")
print(f"  - Embedding dimension: 100")
print(f"  - Epochs: 50")

model_distmult_full = DistMult(
    triples_factory=dataset_full.training,
    embedding_dim=100,
)

training_loop_distmult_full = SLCWATrainingLoop(
    model=model_distmult_full,
    triples_factory=dataset_full.training,
    learning_rate=0.001,
    batch_size=128,
)

print(f"\n  Training...")
for epoch in range(50):
    loss = training_loop_distmult_full.train(num_epochs=1)
    if (epoch + 1) % 10 == 0:
        print(f"    Epoch {epoch + 1}: Loss = {loss:.4f}")

print(f"\n  Evaluating...")
evaluator_distmult_full = RankBasedEvaluator()
metric_results_distmult_full = evaluator_distmult_full.evaluate(
    model=model_distmult_full,
    mapped_triples=dataset_full.testing,
    batch_size=128,
    additional_filter_triples=[dataset_full.training.mapped_triples, dataset_full.validation.mapped_triples],
)

print(f"\n[Part 4] DistMult Results (Full Dataset):")
print(f"  MRR: {metric_results_distmult_full.mean_reciprocal_rank:.4f}")
print(f"  Hits@1: {metric_results_distmult_full.hits_at_1:.4f}")
print(f"  Hits@3: {metric_results_distmult_full.hits_at_3:.4f}")
print(f"  Hits@10: {metric_results_distmult_full.hits_at_10:.4f}")

# ============================================================================
# PART 5: SIZE SENSITIVITY ANALYSIS
# ============================================================================

print("\n" + "="*80)
print("PART 5: SIZE SENSITIVITY ANALYSIS (5k Subset)")
print("="*80)

print(f"\n[Part 5] Training TransE on small dataset...")
model_transe_small = TransE(
    triples_factory=dataset_small.training,
    embedding_dim=100,
)

training_loop_transe_small = SLCWATrainingLoop(
    model=model_transe_small,
    triples_factory=dataset_small.training,
    learning_rate=0.001,
    batch_size=64,
)

for epoch in range(50):
    loss = training_loop_transe_small.train(num_epochs=1)

evaluator_transe_small = RankBasedEvaluator()
metric_results_transe_small = evaluator_transe_small.evaluate(
    model=model_transe_small,
    mapped_triples=dataset_small.testing,
    batch_size=64,
    additional_filter_triples=[dataset_small.training.mapped_triples, dataset_small.validation.mapped_triples],
)

print(f"  TransE (5k) MRR: {metric_results_transe_small.mean_reciprocal_rank:.4f}")

print(f"\n[Part 5] Training DistMult on small dataset...")
model_distmult_small = DistMult(
    triples_factory=dataset_small.training,
    embedding_dim=100,
)

training_loop_distmult_small = SLCWATrainingLoop(
    model=model_distmult_small,
    triples_factory=dataset_small.training,
    learning_rate=0.001,
    batch_size=64,
)

for epoch in range(50):
    loss = training_loop_distmult_small.train(num_epochs=1)

evaluator_distmult_small = RankBasedEvaluator()
metric_results_distmult_small = evaluator_distmult_small.evaluate(
    model=model_distmult_small,
    mapped_triples=dataset_small.testing,
    batch_size=64,
    additional_filter_triples=[dataset_small.training.mapped_triples, dataset_small.validation.mapped_triples],
)

print(f"  DistMult (5k) MRR: {metric_results_distmult_small.mean_reciprocal_rank:.4f}")

# ============================================================================
# PART 6: RESULTS COMPILATION
# ============================================================================

print("\n" + "="*80)
print("PART 6: RESULTS COMPILATION")
print("="*80)

results = {
    "dataset_statistics": {
        "total_triples": len(triples_unique),
        "unique_entities": dataset_full.num_entities,
        "unique_relations": dataset_full.num_relations,
        "train_size": len(dataset_full.training),
        "valid_size": len(dataset_full.validation),
        "test_size": len(dataset_full.testing),
    },
    "models": {
        "TransE": {
            "full_dataset": {
                "mrr": float(metric_results_transe_full.mean_reciprocal_rank),
                "hits_at_1": float(metric_results_transe_full.hits_at_1),
                "hits_at_3": float(metric_results_transe_full.hits_at_3),
                "hits_at_10": float(metric_results_transe_full.hits_at_10),
            },
            "small_dataset": {
                "mrr": float(metric_results_transe_small.mean_reciprocal_rank),
                "hits_at_1": float(metric_results_transe_small.hits_at_1),
                "hits_at_3": float(metric_results_transe_small.hits_at_3),
                "hits_at_10": float(metric_results_transe_small.hits_at_10),
            }
        },
        "DistMult": {
            "full_dataset": {
                "mrr": float(metric_results_distmult_full.mean_reciprocal_rank),
                "hits_at_1": float(metric_results_distmult_full.hits_at_1),
                "hits_at_3": float(metric_results_distmult_full.hits_at_3),
                "hits_at_10": float(metric_results_distmult_full.hits_at_10),
            },
            "small_dataset": {
                "mrr": float(metric_results_distmult_small.mean_reciprocal_rank),
                "hits_at_1": float(metric_results_distmult_small.hits_at_1),
                "hits_at_3": float(metric_results_distmult_small.hits_at_3),
                "hits_at_10": float(metric_results_distmult_small.hits_at_10),
            }
        }
    }
}

# Write results
with open(KGE_DIR / "results.json", 'w') as f:
    json.dump(results, f, indent=2)

# Model comparison
transe_mrr = results["models"]["TransE"]["full_dataset"]["mrr"]
distmult_mrr = results["models"]["DistMult"]["full_dataset"]["mrr"]

winner = "TransE" if transe_mrr > distmult_mrr else "DistMult"
model_comparison = {
    "winner": winner,
    "TransE_MRR": transe_mrr,
    "DistMult_MRR": distmult_mrr,
    "analysis": {
        "model_advantage": f"{winner} achieved higher MRR ({max(transe_mrr, distmult_mrr):.4f})",
        "TransE_strength": "Better for translational geometries and hierarchical knowledge",
        "DistMult_strength": "Better for symmetric relations and multiplicative interactions",
    }
}

with open(KGE_DIR / "model_comparison.json", 'w') as f:
    json.dump(model_comparison, f, indent=2)

# ============================================================================
# SUMMARY AND OUTPUT
# ============================================================================

print("\n" + "="*80)
print("MODULE 5 COMPLETION SUMMARY")
print("="*80)

print(f"\n✅ DATA PREPARATION:")
print(f"   Total triples: {len(triples_unique)}")
print(f"   Unique entities: {dataset_full.num_entities}")
print(f"   Unique relations: {dataset_full.num_relations}")

print(f"\n✅ MODEL RESULTS (Full Dataset):")
print(f"\n  Trans E:")
print(f"    MRR: {transe_mrr:.4f}")
print(f"    Hits@1: {results['models']['TransE']['full_dataset']['hits_at_1']:.4f}")
print(f"    Hits@3: {results['models']['TransE']['full_dataset']['hits_at_3']:.4f}")
print(f"    Hits@10: {results['models']['TransE']['full_dataset']['hits_at_10']:.4f}")

print(f"\n  DistMult:")
print(f"    MRR: {distmult_mrr:.4f}")
print(f"    Hits@1: {results['models']['DistMult']['full_dataset']['hits_at_1']:.4f}")
print(f"    Hits@3: {results['models']['DistMult']['full_dataset']['hits_at_3']:.4f}")
print(f"    Hits@10: {results['models']['DistMult']['full_dataset']['hits_at_10']:.4f}")

print(f"\n✅ SIZE SENSITIVITY:")
print(f"  TransE (Full): {transe_mrr:.4f} → TransE (5k): {results['models']['TransE']['small_dataset']['mrr']:.4f}")
print(f"  DistMult (Full): {distmult_mrr:.4f} → DistMult (5k): {results['models']['DistMult']['small_dataset']['mrr']:.4f}")

print(f"\n📁 OUTPUT FILES:")
print(f"   ✓ data/kge/train.txt ({len(dataset_full.training)} triples)")
print(f"   ✓ data/kge/valid.txt ({len(dataset_full.validation)} triples)")
print(f"   ✓ data/kge/test.txt ({len(dataset_full.testing)} triples)")
print(f"   ✓ kge/results.json")
print(f"   ✓ kge/model_comparison.json")

print(f"\n🏆 BEST MODEL: {winner}")
print(f"   MRR Score: {max(transe_mrr, distmult_mrr):.4f}")

print("\n" + "="*80)
print("✅ MODULE 5: KNOWLEDGE GRAPH EMBEDDINGS COMPLETE")
print("="*80)
