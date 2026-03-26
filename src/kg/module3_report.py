#!/usr/bin/env python3
"""
Module 3: Extract and Report Semantic Relations
Displays example triples and relation statistics.
"""

import json
from pathlib import Path
from collections import defaultdict

from rdflib import Graph, Namespace, RDF, RDFS

ROOT = Path(__file__).resolve().parent
KG_DIR = ROOT / "kg_artifacts"

EX = Namespace("http://example.org/ai-kg/")

print("[Module 3 Report] Loading final expanded graph...")
graph = Graph()
with open(KG_DIR / "expanded_full_v2.ttl", 'r', encoding='utf-8') as f:
    graph.parse(file=f, format="turtle")

print(f"[Module 3 Report] Total triples: {len(graph)}")

# Extract semantic relations
semantic_relations = defaultdict(list)

for s, p, o in graph.triples((None, None, None)):
    p_str = str(p)
    
    # Focus on new semantic relations
    if any(rel in p_str for rel in ["worksOn", "hasResearchArea", "collaboratesWith", 
                                      "publishedOn", "authored", "collaboratedWith", 
                                      "addressesField", "focusesOn", "studiesField",
                                      "relatesToResearch", "builds"]):
        s_label = str(graph.value(s, RDFS.label) or s)
        o_label = str(graph.value(o, RDFS.label) or o)
        rel_name = p_str.split("/")[-1]
        semantic_relations[rel_name].append((s_label, o_label))

# Generate report
print("\n" + "="*80)
print("MODULE 3 SEMANTIC ENRICHMENT REPORT")
print("="*80)

# Summary statistics
print("\n📊 EXPANSION STATISTICS:")
print(f"  Base graph (Module 2):     1,458 triples")
print(f"  After enrichment:          {len(graph):,} triples")
print(f"  Total added:               +{len(graph) - 1458} triples")
print(f"  Growth rate:               +{round((len(graph) - 1458) / 1458 * 100, 1)}%")

# Relation types created
print(f"\n🔗 NEW SEMANTIC RELATION TYPES CREATED:")
total_semantic = 0
for i, (rel_type, examples) in enumerate(sorted(semantic_relations.items(), 
                                                 key=lambda x: len(x[1]), reverse=True), 1):
    if i <= 8:
        count = len(examples)
        total_semantic += count
        print(f"  {i}. {rel_type:25s}: {count:3d} triples")

print(f"\n  Total semantic relations:  {total_semantic} new triples")

# Show specific examples
print(f"\n✨ EXAMPLE TRIPLES (5 per relation type):")

example_count = 0
for rel_type in ["worksOn", "hasResearchArea", "collaboratesWith", "authored", "collaboratedWith"]:
    if rel_type in semantic_relations:
        examples = semantic_relations[rel_type][:5]
        if examples:
            print(f"\n  📌 {rel_type}:")
            for s_label, o_label in examples:
                # Clean up labels
                s_clean = s_label.replace("http://example.org/ai-kg/entity/", "").replace("http://", "").replace("example.org/ai-kg/", "")
                o_clean = o_label.replace("http://example.org/ai-kg/field/", "").replace("http://", "").replace("example.org/ai-kg/", "")
                
                # Capitalize properly
                s_clean = s_clean.replace("-", " ").title() if "/" not in s_clean else s_clean
                o_clean = o_clean.replace("-", " ").title() if "/" not in o_clean else o_clean
                
                print(f"     {s_clean:30s} → {rel_type:20s} → {o_clean:30s}")
                example_count += 1

# Research domains analysis
print(f"\n🎯 RESEARCH DOMAINS COVERED:")
research_fields = set()
for s, p, o in graph.triples((None, RDF.type, EX.ResearchField)):
    label = str(graph.value(s, RDFS.label) or "Unknown")
    research_fields.add(label)

for i, field in enumerate(sorted(research_fields)[:8], 1):
    print(f"  {i}. {field}")

# Entity analysis
print(f"\n👥 ENRICHED ENTITIES:")
entities_with_relations = set()
for s, p, o in graph.triples((None, None, None)):
    p_str = str(p)
    if any(rel in p_str for rel in ["worksOn", "hasResearchArea", "collaboratesWith", "authored"]):
        s_label = str(graph.value(s, RDFS.label) or s)
        entities_with_relations.add(s_label)

print(f"  Entities with semantic relations: {len(entities_with_relations)}")
for entity in sorted(list(entities_with_relations))[:5]:
    entity_clean = entity.replace("http://example.org/ai-kg/entity/", "").title() if "/" in entity else entity
    print(f"    - {entity_clean}")

# Generate final statistics JSON
module3_stats = {
    "module": 3,
    "phase": "semantic_enrichment",
    "execution_summary": {
        "base_graph_triples": 1458,
        "enriched_graph_triples": len(graph),
        "total_triples_added": len(graph) - 1458,
        "growth_percent": round((len(graph) - 1458) / 1458 * 100, 1),
    },
    "semantic_relations": {
        "types_created": len(semantic_relations),
        "total_relations": total_semantic,
        "by_type": {rel: len(examples) for rel, examples in semantic_relations.items()},
    },
    "research_fields": {
        "count": len(research_fields),
        "samples": sorted(list(research_fields))[:8],
    },
    "entities_enriched": {
        "count": len(entities_with_relations),
        "enrichment_type": "research domain linking",
    },
    "example_triples": [
        f"{s} → {rel} → {o}" 
        for rel in ["worksOn", "hasResearchArea", "collaboratesWith"]
        if rel in semantic_relations
        for s, o in semantic_relations[rel][:2]
    ]
}

output_file = KG_DIR / "module3_semantic_relations.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(module3_stats, f, indent=2, ensure_ascii=False)

print(f"\n📄 Statistics saved to: module3_semantic_relations.json")

print("\n" + "="*80)
print("✅ MODULE 3 COMPLETE: Semantic Enrichment Successful")
print("="*80)
print(f"\nKey Achievements:")
print(f"  ✓ Added {len(graph) - 1458} semantic triples")
print(f"  ✓ Created {len(semantic_relations)} new relation types")
print(f"  ✓ Mapped {len(entities_with_relations)} entities to research domains")
print(f"  ✓ Generated {len(research_fields)} research field entities")
print(f"\nReady for downstream tasks:")
print(f"  → KGE embedding training")
print(f"  → Knowledge-enhanced QA")
print(f"  → SPARQL reasoning")
print("\n" + "="*80)
