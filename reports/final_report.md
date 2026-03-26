# Final Project Report

## 1. Introduction

This project implements a complete pipeline from unstructured web text to a queryable and explainable Knowledge Graph (KG) for Information Retrieval and NLP. The pipeline includes six modules:

1. Data acquisition and information extraction.
2. RDF knowledge base modeling and entity alignment.
3. Knowledge base expansion and semantic enrichment.
4. Rule-based reasoning on both benchmark and domain KGs.
5. Knowledge graph embedding training and evaluation.
6. KG-grounded RAG with NL-to-SPARQL and self-repair.

The objective is not only to build the KG, but also to validate it through reasoning, embedding quality, and question-answering grounded in explicit triples.

## 2. Module 1: Data Acquisition and Information Extraction

### 2.1 Crawler and Cleaning Pipeline

The acquisition stack is implemented under `src/crawl/` and includes:

1. Controlled crawling with polite behavior (robots checking, delays, explicit `User-Agent`).
2. Cleaning and normalization in `src/crawl/cleaning.py`.
3. Export of cleaned content to `data/cleaned/`.

### 2.2 Named Entity Recognition

Entity extraction is implemented in `src/ie/ner.py` and serialized in JSONL/CSV artifacts under `data/`. Each entity mention includes metadata used downstream by alignment and confidence-based filtering.

### 2.3 Ambiguity Tracking (Three Documented Cases)

Although the final filtered ambiguity file contains no unresolved cases (`data/ambiguity_examples_final.json`), three representative ambiguity examples were documented during analysis and cleaning:

1. `ai` as `GPE` vs `ORG`.
2. `ELLIS Fellows` as `PERSON` vs `ORG`.
3. `Paris` as `GPE` vs `ORG` context reference.

These examples were handled through contextual disambiguation and post-filtering so unresolved ambiguous entries are minimized in final artifacts.

## 3. Module 2 and 3: KB Modeling, Alignment, and Expansion

### 3.1 RDF/OWL Modeling and Alignment

Core KG artifacts are stored in `kg_artifacts/`:

1. `ontology.ttl` for schema classes/properties.
2. `graph.ttl` and `base_graph.ttl` for base graph triples.
3. `alignment.ttl` and `aligned_graph.ttl` for linked entities.
4. `expanded.nt` and `expanded_full_v2.ttl` for expanded graphs.

Entity linking and predicate alignment are performed in the Module 2 pipeline with confidence-aware matching and accepted/rejected candidate tracking.

### 3.2 Before/After Statistics (Required Comparison)

From `kg_artifacts/module2_final_stats.json` and `kg_artifacts/kb_stats.json`:

| Stage | Triple Count | Entity Count | Linked Entities | Linked % |
|---|---:|---:|---:|---:|
| Before expansion (aligned) | 1381 | 151 | 35 | 23.18 |
| After expansion (step 5) | 1458 | 151 | 35 | 23.18 |
| After semantic enrichment (module 3) | 1653 | 151 | 35 | 23.18 |

Expansion effect:

1. +77 triples in initial expansion (`+5.58%`).
2. +195 triples in semantic enrichment (`+13.4%` over base graph).

### 3.3 SPARQL Expansion Strategy

The expansion strategy combines deterministic rules and SPARQL-driven graph augmentation:

1. Infer collaboration and affiliation links from co-occurrence and known organization relations.
2. Materialize research-area semantics (`hasResearchArea`, `worksOn`, `addressesField`).
3. Add provenance-like fields (`sourceUrl`, `confidenceScore`, extraction metadata) for traceability.

Representative query pattern:

```sparql
PREFIX ex: <http://example.org/ai-kg/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?org ?area
WHERE {
	?org ex:hasResearchArea ?area .
	OPTIONAL { ?org rdfs:label ?label }
}
```

## 4. Module 4: Rule-Based Reasoning

Reasoning is implemented in `src/reason/run_module4_reasoning.py` with two parts.

### 4.1 Family Ontology Reasoning (`family.owl`)

The script explicitly loads `family.owl` through Owlready2 and applies SWRL-style rules:

1. `isParentOf(x,y) ∧ isParentOf(y,z) -> isGrandparentOf(x,z)`
2. `isFatherOf(x,y) ∧ isFatherOf(y,z) -> isGrandFatherOf(x,z)`
3. `isParentOf(x,y) ∧ isParentOf(x,z) ∧ y != z -> isSiblingOf(y,z)`

Output: `src/reason/family_inferences.txt`

### 4.2 Domain KB Reasoning

The same module applies SWRL-style rules to the project KB (`kg_artifacts/expanded_full_v2.ttl`):

1. `affiliatedWith + locatedIn -> worksInCountry`
2. `collaboratesWith + hasResearchArea -> sharesResearchField`
3. `worksOn + hasResearchArea -> collaboratesInField`

Output: `src/reason/kb_inferences.txt`

## 5. Module 5: KGE Modeling and Evaluation

### 5.1 Models and Data

Two KGE models were trained and compared:

1. `TransE`
2. `DistMult`

Artifacts are available in:

1. `reports/kge/results.json`
2. `reports/kge/model_comparison.json`
3. `reports/kge/transE_optimization.json`
4. `reports/kge/qualitative_analysis.json`

### 5.2 Main Metrics (Test)

Best TransE configuration (KB + inferred triples):

1. `MRR = 0.3719`
2. `Hits@1 = 0.1604`
3. `Hits@3 = 0.5377`
4. `Hits@10 = 0.7358`

DistMult (full dataset baseline):

1. `MRR = 0.0162`
2. `Hits@1 = 0.0000`
3. `Hits@3 = 0.0200`
4. `Hits@10 = 0.0400`

Optimization summary:

1. TransE baseline MRR: `0.0996`
2. Optimized/inferred MRR: `0.3719`
3. Improvement from inferred triples over tuned base KB: `+0.0210` MRR

### 5.3 Size Sensitivity

The official requirement mentions 20k/50k/full settings. In this project, total train triples are below those thresholds (`1096` train triples), so fixed-size settings collapse to the same full data regime. Therefore, sensitivity is analyzed on available splits (`small` vs `full`) and documented in `reports/kge/model_comparison.json`.

### 5.4 Qualitative Embedding Analysis

Nearest-neighbor analysis for sampled entities is provided in `reports/kge/qualitative_analysis.json` for both TransE and DistMult. This serves as qualitative evidence of embedding space behavior and semantic locality.

Additionally, a 2D embedding projection figure is provided at `reports/kge/tsne_projection.png` with generation metadata in `reports/kge/tsne_projection_meta.json`.

## 6. Module 6: KG-Grounded RAG

### 6.1 Pipeline

`rag/pipeline.py` implements:

1. Schema-aware NL-to-SPARQL generation.
2. Query execution against KG artifacts.
3. Self-repair loop (retry on parse/query errors, up to bounded attempts).
4. Answer synthesis constrained by returned triples.

### 6.2 Evaluation

From `rag/eval_results.json`:

1. Number of questions: `5`
2. KG query success rate: `1.00`
3. Average supporting triples: `4.6`

The evaluation includes baseline (no KG grounding) and KG-grounded outputs for direct comparison.

### 6.3 Ollama Integration Note

The repository includes local Ollama setup instructions for LLM-backed generation. In this submission, final answers are KG-grounded through SPARQL result evidence; the LLM component is used in a controlled generation role around that grounded context.

## 7. Reproducibility and Repository Quality

### 7.1 Environment

1. Python `3.10+` (validated in workspace on `3.14.3`).
2. Dependencies in `requirements.txt`.
3. Hardware guidance documented in `README.md`.

### 7.2 File Organization

The repository follows module-oriented structure with separate folders for source code, KG artifacts, reports, data, and RAG demo outputs.

### 7.3 Re-run Commands

Key entry points:

```bash
python src/crawl/run_module1.py
python src/ie/ner.py
python src/kg/module2_pipeline.py
python src/kg/run_step3.py
python src/kg/run_step5.py
python src/kg/run_module3_enrichment_enhanced.py
python src/reason/run_module4_reasoning.py
python src/kge/run_module5.py
python src/kge/run_module5_optimize.py
python rag/demo.py --eval
```

## 8. Critical Reflection

Strengths:

1. End-to-end implementation from raw text to explainable QA.
2. Clear artifact trail for each module.
3. Strong TransE improvement after tuning and inferred-triple augmentation.
4. Reliable KG query execution in RAG evaluation.

Limitations:

1. Small dataset size constrains formal 20k/50k/full sensitivity benchmarks.
2. Some extracted labels remain noisy due to web-source heterogeneity.
3. DistMult underperformed significantly on this dataset.

Future work:

1. Expand corpus and improve deduplication before IE.
2. Add larger-scale KGE sensitivity with strict 20k/50k/full partitions.
3. Add explicit 2D embedding visualizations and cluster diagnostics.
4. Improve label normalization for cleaner KG entities.

## 9. Conclusion

The project satisfies the full six-module workflow and demonstrates that combining KG construction, reasoning, embeddings, and KG-grounded RAG yields explainable and reproducible IR/NLP results. The strongest quantitative outcome is the optimized TransE model (`MRR = 0.3719`, `Hits@10 = 0.7358`), while the strongest system-level outcome is robust KG-grounded question answering with full query success on the evaluation set.
