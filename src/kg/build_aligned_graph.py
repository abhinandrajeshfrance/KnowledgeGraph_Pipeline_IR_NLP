#!/usr/bin/env python3
"""Build aligned graph with existing auto-linked entities."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef

KG_DIR = ROOT / "kg_artifacts"
LINK_DIR = KG_DIR / "linking"
BASE_GRAPH_FILE = KG_DIR / "base_graph.ttl"
ALIGNED_GRAPH_FILE = KG_DIR / "aligned_graph.ttl"
AUTO_LINKS_FILE = LINK_DIR / "auto_links.jsonl"

EX = Namespace("http://example.org/ai-kg/")
WD = Namespace("http://www.wikidata.org/entity/")

print("[AlignedGraph] Loading base graph...")
graph = Graph()
graph.parse(str(BASE_GRAPH_FILE), format="turtle")
graph.bind("ex", EX)
graph.bind("rdf", RDF)
graph.bind("rdfs", RDFS)
graph.bind("owl", OWL)
graph.bind("wd", WD)

# Load auto-links and add owl:sameAs statements
print(f"[AlignedGraph] Loading auto-links from {AUTO_LINKS_FILE}...")
auto_links_count = 0
if AUTO_LINKS_FILE.exists():
    with open(AUTO_LINKS_FILE) as f:
        for line in f:
            if line.strip():
                link = json.loads(line)
                local_uri = URIRef(link["local_uri"])
                qid = link["wikidata_qid"]
                graph.add((local_uri, OWL.sameAs, WD[qid]))
                auto_links_count += 1
                print(f"  Added link: {link['entity_text']} -> {qid}")

print(f"[AlignedGraph] Added {auto_links_count} owl:sameAs statements")

# Save aligned graph
print(f"[AlignedGraph] Saving aligned graph...")
graph.serialize(destination=str(ALIGNED_GRAPH_FILE), format="turtle")

print(f"[AlignedGraph] Done! Graph saved to {ALIGNED_GRAPH_FILE}")
print(f"[AlignedGraph] Triple count: {len(graph)}")
