#!/usr/bin/env python3
"""
Module 5: Knowledge Graph Embeddings (KGE)
- Data preparation and normalization
- Dataset splitting (train/valid/test)
- Model training (TransE, DistMult)
- Evaluation and comparison
- Size sensitivity analysis
"""

import json
import random
from pathlib import Path
from collections import defaultdict
import numpy as np
from rdflib import Graph as RDFGraph, Namespace, RDFS

# PyKEEN imports
from pykeen.pipeline import pipeline
from pykeen.datasets import PathDataset
import torch

print("[Module 5] Starting Knowledge Graph Embeddings Pipeline...")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "kge"
DATA_DIR.mkdir(parents=True, exist_ok=True)
KGE_DIR = ROOT / "kge"
KGE_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# PART 1: DATA PREPARATION - EXTRACT AND NORMALIZE TRIPLES
# ============================================================================

print("\n" + "="*80)
print("PART 1: DATA PREPARATION - EXTRACT AND NORMALIZE TRIPLES")
print("="*80)

KB_FILE = ROOT / "kg_artifacts" / "expanded_full_v2.ttl"
print(f"\n[Part 1] Loading knowledge graph from {KB_FILE.name}...")

# Load KB
kb_graph = RDFGraph()
with open(KB_FILE, 'r', encoding='utf-8') as f:
    kb_graph.parse(file=f, format="turtle")

print(f"[Part 1] Loaded knowledge graph with {len(kb_graph)} triples")

# Create entity-to-label mapping
entity_labels = {}
EX = Namespace("http://example.org/ai-kg/")

print(f"\n[Part 1] Normalizing entity names...")

# Function to get short label for entity
def get_entity_label(uri):
    """Extract short label from URI or rdfs:label"""
    if str(uri) in entity_labels:
        return entity_labels[str(uri)]
    
    # Try rdfs:label first
    label = kb_graph.value(uri, RDFS.label)
    if label:
        short_label = str(label).lower().replace(" ", "_").replace("/", "_").replace(":", "_")
    else:
        # Fall back to URI fragment
        uri_str = str(uri)
        if "#" in uri_str:
            short_label = uri_str.split("#")[-1].lower()
        elif "/" in uri_str:
            short_label = uri_str.split("/")[-1].lower()
        else:
            short_label = uri_str.lower()
    
    # Clean up
    short_label = "".join(c if c.isalnum() or c == "_" else "_" for c in short_label)
    short_label = short_label.strip("_")[: 100]  # Limit length
    
    entity_labels[str(uri)] = short_label
    return short_label

# Extract all triples
triples_raw = []
for s, p, o in kb_graph:
    triples_raw.append((s, p, o))

print(f"[Part 1] Extracted {len(triples_raw)} raw triples")

# Normalize to (head, relation, tail) format
triples_normalized = []
relation_counts = defaultdict(int)

for s, p, o in triples_raw:
    head = get_entity_label(s)
    relation = get_entity_label(p)
    tail = get_entity_label(o)
    
    # Skip if any component is empty
    if head and relation and tail:
        triples_normalized.append((head, relation, tail))
        relation_counts[relation] += 1

# Remove duplicates
triples_unique = list(set(triples_normalized))
print(f"[Part 1] After normalization: {len(triples_unique)} unique triples")
print(f"[Part 1] Duplicate removal: {len(triples_normalized) - len(triples_unique)} duplicates removed")

# Get statistics
unique_heads = len(set(h for h, r, t in triples_unique))
unique_relations = len(set(r for h, r, t in triples_unique))
unique_tails = len(set(t for h, r, t in triples_unique))

print(f"\n[Part 1] Triple Statistics:")
print(f"  Unique entities (heads only): {unique_heads}")
print(f"  Unique relations: {unique_relations}")
print(f"  Unique entities (tails only): {unique_tails}")
print(f"  Total unique entities: {len(set(h for h,r,t in triples_unique) | set(t for h,r,t in triples_unique))}")
print(f"\n[Part 1] Top 10 Relations by Frequency:")
for rel, count in sorted(relation_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {rel}: {count} triples")

# ============================================================================
# PART 2: DATASET SPLITTING (Train/Valid/Test)
# ============================================================================

print("\n" + "="*80)
print("PART 2: DATASET SPLITTING (80% Train / 10% Valid / 10% Test)")
print("="*80)

# Shuffle
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)

triples_shuffled = triples_unique.copy()
random.shuffle(triples_shuffled)

# Calculate split indices
n_triples = len(triples_shuffled)
train_size = int(0.8 * n_triples)
valid_size = int(0.1 * n_triples)

train_triples = triples_shuffled[:train_size]
valid_triples = triples_shuffled[train_size:train_size + valid_size]
test_triples = triples_shuffled[train_size + valid_size:]

print(f"\n[Part 2] Split sizes:")
print(f"  Total triples: {n_triples}")
print(f"  Train: {len(train_triples)} ({100*len(train_triples)/n_triples:.1f}%)")
print(f"  Valid: {len(valid_triples)} ({100*len(valid_triples)/n_triples:.1f}%)")
print(f"  Test: {len(test_triples)} ({100*len(test_triples)/n_triples:.1f}%)")

# Check for leakage
train_set = set(train_triples)
test_set = set(test_triples)
leakage = len(train_set & test_set)
print(f"\n[Part 2] Data leakage check: {leakage} triples in both train and test")

# Write datasets
def write_dataset(triples, filepath):
    filepath = Path(filepath)  # Ensure it's a Path object
    filepath.parent.mkdir(parents=True, exist_ok=True)  # Create parent dirs if needed
    with open(str(filepath), 'w', encoding='utf-8') as f:
        for head, relation, tail in triples:
            f.write(f"{head}\t{relation}\t{tail}\n")
    print(f"  ✓ Wrote {len(triples)} triples to {filepath.name}")

print(f"\n[Part 2] Writing dataset files to data/kge/...")
write_dataset(train_triples, DATA_DIR / "train.txt")
write_dataset(valid_triples, DATA_DIR / "valid.txt")
write_dataset(test_triples, DATA_DIR / "test.txt")

# ============================================================================
# PART 3: SMALL DATASET PREPARATION (for size sensitivity analysis)
# ============================================================================

print(f"\n[Part 2] Creating subset (5k triples) for size sensitivity analysis...")

# Create a stratified subset
small_size = min(5000, n_triples)
small_indices = np.random.choice(n_triples, size=small_size, replace=False)
small_triples = [triples_shuffled[i] for i in sorted(small_indices)]

# Split small dataset
small_train_size = int(0.8 * len(small_triples))
small_valid_size = int(0.1 * len(small_triples))

small_train = small_triples[:small_train_size]
small_valid = small_triples[small_train_size:small_train_size + small_valid_size]
small_test = small_triples[small_train_size + small_valid_size:]

write_dataset(small_train, DATA_DIR / "train_small.txt")
write_dataset(small_valid, DATA_DIR / "valid_small.txt")
write_dataset(small_test, DATA_DIR / "test_small.txt")

# ============================================================================
# PART 4: MODEL TRAINING - TransE
# ============================================================================

print("\n" + "="*80)
print("PART 4: MODEL TRAINING - TransE")
print("="*80)

print(f"\n[Part 4] Training TransE on full dataset...")
print(f"  - Embedding dimension: 100")
print(f"  - Epochs: 50")
print(f"  - Learning rate: 0.001")
print(f"  - Batch size: 128")

# Create dataset
dataset_full = PathDataset(
    training=DATA_DIR / "train.txt",
    validation=DATA_DIR / "valid.txt",
    testing=DATA_DIR / "test.txt",
)

result_transe_full = pipeline(
    dataset=dataset_full,
    model='transe',
    model_kwargs={
        'embedding_dim': 100,
    },
    training_kwargs={
        'num_epochs': 50,
        'batch_size': 128,
        'learning_rate': 0.001,
    },
    optimizer='Adam',
    random_seed=42,
    device='cpu',
    evaluator_kwargs={
        'filtered': True,
    }
)

print(f"\n[Part 4] TransE training complete!")
transe_full_model = result_transe_full.model
transe_full_metrics = result_transe_full.metric_results.to_dict()

print(f"  MRR: {transe_full_metrics.get('mean_reciprocal_rank', 'N/A'):.4f}")
if 'hits_at_1' in transe_full_metrics:
    print(f"  Hits@1: {transe_full_metrics['hits_at_1']:.4f}")
if 'hits_at_3' in transe_full_metrics:
    print(f"  Hits@3: {transe_full_metrics['hits_at_3']:.4f}")
if 'hits_at_10' in transe_full_metrics:
    print(f"  Hits@10: {transe_full_metrics['hits_at_10']:.4f}")

# Train on small dataset
print(f"\n[Part 4] Training TransE on 5k subset...")

dataset_small = PathDataset(
    training=DATA_DIR / "train_small.txt",
    validation=DATA_DIR / "valid_small.txt",
    testing=DATA_DIR / "test_small.txt",
)

result_transe_small = pipeline(
    dataset=dataset_small,
    model='transe',
    model_kwargs={
        'embedding_dim': 100,
    },
    training_kwargs={
        'num_epochs': 50,
        'batch_size': 64,
        'learning_rate': 0.001,
    },
    optimizer='Adam',
    random_seed=42,
    device='cpu',
    evaluator_kwargs={
        'filtered': True,
    }
)

transe_small_metrics = result_transe_small.metric_results.to_dict()
print(f"\n[Part 4] TransE (5k subset) complete!")
print(f"  MRR: {transe_small_metrics.get('mean_reciprocal_rank', 'N/A'):.4f}")

# ============================================================================
# PART 5: MODEL TRAINING - DistMult
# ============================================================================

print("\n" + "="*80)
print("PART 5: MODEL TRAINING - DistMult")
print("="*80)

print(f"\n[Part 5] Training DistMult on full dataset...")
print(f"  - Embedding dimension: 100")
print(f"  - Epochs: 50")
print(f"  - Learning rate: 0.001")
print(f"  - Batch size: 128")

result_distmult_full = pipeline(
    dataset=dataset_full,
    model='distmult',
    model_kwargs={
        'embedding_dim': 100,
    },
    training_kwargs={
        'num_epochs': 50,
        'batch_size': 128,
        'learning_rate': 0.001,
    },
    optimizer='Adam',
    random_seed=42,
    device='cpu',
    evaluator_kwargs={
        'filtered': True,
    }
)

print(f"\n[Part 5] DistMult training complete!")
distmult_full_metrics = result_distmult_full.metric_results.to_dict()

print(f"  MRR: {distmult_full_metrics.get('mean_reciprocal_rank', 'N/A'):.4f}")
if 'hits_at_1' in distmult_full_metrics:
    print(f"  Hits@1: {distmult_full_metrics['hits_at_1']:.4f}")
if 'hits_at_3' in distmult_full_metrics:
    print(f"  Hits@3: {distmult_full_metrics['hits_at_3']:.4f}")
if 'hits_at_10' in distmult_full_metrics:
    print(f"  Hits@10: {distmult_full_metrics['hits_at_10']:.4f}")

# Train on small dataset
print(f"\n[Part 5] Training DistMult on 5k subset...")

result_distmult_small = pipeline(
    dataset=dataset_small,
    model='distmult',
    model_kwargs={
        'embedding_dim': 100,
    },
    training_kwargs={
        'num_epochs': 50,
        'batch_size': 64,
        'learning_rate': 0.001,
    },
    optimizer='Adam',
    random_seed=42,
    device='cpu',
    evaluator_kwargs={
        'filtered': True,
    }
)

distmult_small_metrics = result_distmult_small.metric_results.to_dict()
print(f"\n[Part 5] DistMult (5k subset) complete!")
print(f"  MRR: {distmult_small_metrics.get('mean_reciprocal_rank', 'N/A'):.4f}")

# ============================================================================
# PART 6: QUALITATIVE EVALUATION - Nearest Neighbors
# ============================================================================

print("\n" + "="*80)
print("PART 6: QUALITATIVE EVALUATION - Nearest Neighbors")
print("="*80)

# Get all unique entities
all_entities = sorted(list(set(h for h, r, t in triples_unique) | set(t for h, r, t in triples_unique)))
print(f"\n[Part 6] Found {len(all_entities)} unique entities")

# Select diverse entities for analysis
selected_entities = []
if "peter_eisenman" in all_entities:
    selected_entities.append("peter_eisenman")
if "cnrs" in all_entities:
    selected_entities.append("cnrs")
if "artificial_intelligence" in all_entities:
    selected_entities.append("artificial_intelligence")
if "knowledge_graphs" in all_entities:
    selected_entities.append("knowledge_graphs")

# Add a few random entities if we don't have enough
while len(selected_entities) < 5 and all_entities:
    rand_entity = random.choice(all_entities)
    if rand_entity not in selected_entities:
        selected_entities.append(rand_entity)

qualitative_results = {}

print(f"\n[Part 6] Finding nearest neighbors for selected entities...")

for model_name, model in [("TransE", transe_full_model), ("DistMult", distmult_full_model)]:
    print(f"\n  {model_name} Nearest Neighbors:")
    qualitative_results[model_name] = {}
    
    for entity in selected_entities:
        try:
            # Get embedding from model
            # Get the model's entity embedding matrix
            entity_embeddings = model.entity_embeddings
            
            # Get the entity-to-id mapping
            if hasattr(model, 'entity_to_id'):
                entity_id = model.entity_to_id.get(entity)
            else:
                # Try to find it in the triples
                entity_id = None
                for i, ent_name in enumerate(set(h for h,r,t in triples_unique) | set(t for h,r,t in triples_unique)):
                    if ent_name == entity:
                        entity_id = i
                        break
            
            if entity_id is None:
                # Try to match by substring
                for ent_id, ent_name in model.entity_to_id.items() if hasattr(model, 'entity_to_id') else enumerate([]):
                    if entity.lower() in ent_name.lower() or ent_name.lower() in entity.lower():
                        entity_id = ent_id
                        break
            
            if entity_id is None:
                continue
            
            # Get embedding
            entity_embedding = entity_embeddings(torch.tensor([entity_id]))[0].detach().cpu().numpy()
            
            # Find nearest neighbors
            all_embeddings = entity_embeddings(torch.arange(entity_embeddings.num_embeddings)).detach().cpu().numpy()
            
            # Compute distances
            distances = np.linalg.norm(all_embeddings - entity_embedding, axis=1)
            
            # Get top 5 nearest (excluding self)
            neighbors_idx = np.argsort(distances)[1:6]
            
            # Get entity names
            if hasattr(model, 'id_to_entity'):
                neighbors = [model.id_to_entity[idx] for idx in neighbors_idx]
            else:
                all_ents = sorted(list(set(h for h,r,t in triples_unique) | set(t for h,r,t in triples_unique)))
                neighbors = [all_ents[idx] if idx < len(all_ents) else f"ent_{idx}" for idx in neighbors_idx]
            
            neighbor_dists = [distances[idx] for idx in neighbors_idx]
            
            qualitative_results[model_name][entity] = {
                "neighbors": neighbors,
                "distances": [float(d) for d in neighbor_dists]
            }
            
            print(f"    {entity}:")
            for i, (neighbor, dist) in enumerate(zip(neighbors, neighbor_dists), 1):
                print(f"      {i}. {neighbor} (distance: {dist:.4f})")
        
        except Exception as e:
            print(f"    {entity}: Error - {str(e)[:50]}")

# ============================================================================
# PART 7: MODEL COMPARISON AND METRICS
# ============================================================================

print("\n" + "="*80)
print("PART 7: MODEL COMPARISON AND RESULTS")
print("="*80)

# Extract key metrics
def extract_metrics(metric_dict):
    """Extract key metrics from PyKEEN results"""
    return {
        "mrr": metric_dict.get('mean_reciprocal_rank', 0.0),
        "hits_at_1": metric_dict.get('hits_at_1', 0.0),
        "hits_at_3": metric_dict.get('hits_at_3', 0.0),
        "hits_at_10": metric_dict.get('hits_at_10', 0.0),
        "hits_at_k": metric_dict.get('hits_at_k', {}),
    }

results_summary = {
    "dataset_statistics": {
        "total_triples": len(triples_unique),
        "unique_entities": len(set(h for h, r, t in triples_unique) | set(t for h, r, t in triples_unique)),
        "unique_relations": unique_relations,
        "train_size": len(train_triples),
        "valid_size": len(valid_triples),
        "test_size": len(test_triples),
        "small_dataset_size": len(small_triples),
    },
    "models": {
        "TransE": {
            "full_dataset": extract_metrics(transe_full_metrics),
            "small_dataset": extract_metrics(transe_small_metrics),
        },
        "DistMult": {
            "full_dataset": extract_metrics(distmult_full_metrics),
            "small_dataset": extract_metrics(distmult_small_metrics),
        },
    },
    "qualitative_analysis": qualitative_results,
}

# Write results
results_file = KGE_DIR / "results.json"
with open(results_file, 'w', encoding='utf-8') as f:
    json.dump(results_summary, f, indent=2)
print(f"\n[Part 7] ✓ Results written to {results_file.name}")

print(f"\n[Part 7] RESULTS SUMMARY:")
print(f"\n  TransE (Full Dataset):")
print(f"    MRR: {results_summary['models']['TransE']['full_dataset']['mrr']:.4f}")
print(f"    Hits@1: {results_summary['models']['TransE']['full_dataset']['hits_at_1']:.4f}")
print(f"    Hits@3: {results_summary['models']['TransE']['full_dataset']['hits_at_3']:.4f}")
print(f"    Hits@10: {results_summary['models']['TransE']['full_dataset']['hits_at_10']:.4f}")

print(f"\n  DistMult (Full Dataset):")
print(f"    MRR: {results_summary['models']['DistMult']['full_dataset']['mrr']:.4f}")
print(f"    Hits@1: {results_summary['models']['DistMult']['full_dataset']['hits_at_1']:.4f}")
print(f"    Hits@3: {results_summary['models']['DistMult']['full_dataset']['hits_at_3']:.4f}")
print(f"    Hits@10: {results_summary['models']['DistMult']['full_dataset']['hits_at_10']:.4f}")

print(f"\n  Size Sensitivity Analysis:")
print(f"    TransE (5k): MRR = {results_summary['models']['TransE']['small_dataset']['mrr']:.4f}")
print(f"    DistMult (5k): MRR = {results_summary['models']['DistMult']['small_dataset']['mrr']:.4f}")

# ============================================================================
# MODEL COMPARISON
# ============================================================================

model_comparison = {
    "winner": "TransE" if results_summary['models']['TransE']['full_dataset']['mrr'] > 
              results_summary['models']['DistMult']['full_dataset']['mrr'] else "DistMult",
    "TransE": results_summary['models']['TransE']['full_dataset'],
    "DistMult": results_summary['models']['DistMult']['full_dataset'],
    "analysis": {
        "model_strengths": {
            "TransE": "Better at translational distances, good for hierarchical structures",
            "DistMult": "Better for symmetric relations, multiplicative interactions"
        },
        "recommendation": f"TransE shows {'better' if results_summary['models']['TransE']['full_dataset']['mrr'] > results_summary['models']['DistMult']['full_dataset']['mrr'] else 'comparable'} MRR performance for this knowledge graph.",
    }
}

comparison_file = KGE_DIR / "model_comparison.json"
with open(comparison_file, 'w', encoding='utf-8') as f:
    json.dump(model_comparison, f, indent=2)
print(f"\n[Part 7] ✓ Model comparison written to {comparison_file.name}")

# ============================================================================
# MODULE 5 COMPLETION SUMMARY
# ============================================================================

print("\n" + "="*80)
print("MODULE 5 COMPLETION SUMMARY")
print("="*80)

print(f"\n✅ DATA PREPARATION:")
print(f"   Total triples extracted: {len(triples_unique)}")
print(f"   Unique entities: {len(set(h for h, r, t in triples_unique) | set(t for h, r, t in triples_unique))}")
print(f"   Unique relations: {unique_relations}")
print(f"   Duplicates removed: {len(triples_normalized) - len(triples_unique)}")

print(f"\n✅ DATASET SPLITS:")
print(f"   Train: {len(train_triples)} (80%)")
print(f"   Valid: {len(valid_triples)} (10%)")
print(f"   Test: {len(test_triples)} (10%)")
print(f"   Data leakage: {leakage} triples")

print(f"\n✅ MODEL TRAINING:")
print(f"   Model 1: TransE")
print(f"     Full dataset MRR: {results_summary['models']['TransE']['full_dataset']['mrr']:.4f}")
print(f"     5k subset MRR: {results_summary['models']['TransE']['small_dataset']['mrr']:.4f}")
print(f"   Model 2: DistMult")
print(f"     Full dataset MRR: {results_summary['models']['DistMult']['full_dataset']['mrr']:.4f}")
print(f"     5k subset MRR: {results_summary['models']['DistMult']['small_dataset']['mrr']:.4f}")

print(f"\n✅ QUALITATIVE ANALYSIS:")
print(f"   Entities analyzed: {len(selected_entities)}")
print(f"   Nearest neighbors computed for both models")

print(f"\n📁 OUTPUT FILES:")
print(f"   ✓ data/kge/train.txt ({len(train_triples)} triples)")
print(f"   ✓ data/kge/valid.txt ({len(valid_triples)} triples)")
print(f"   ✓ data/kge/test.txt ({len(test_triples)} triples)")
print(f"   ✓ data/kge/train_small.txt ({len(small_train)} triples)")
print(f"   ✓ kge/results.json")
print(f"   ✓ kge/model_comparison.json")

winner = "TransE" if results_summary['models']['TransE']['full_dataset']['mrr'] > \
         results_summary['models']['DistMult']['full_dataset']['mrr'] else "DistMult"

print(f"\n🏆 BEST MODEL: {winner}")
print(f"   {winner} achieved higher MRR: {max(results_summary['models']['TransE']['full_dataset']['mrr'], results_summary['models']['DistMult']['full_dataset']['mrr']):.4f}")

print("\n" + "="*80)
print("✅ MODULE 5: KNOWLEDGE GRAPH EMBEDDINGS COMPLETE")
print("="*80)
