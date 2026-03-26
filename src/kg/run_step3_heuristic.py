#!/usr/bin/env python3
"""
Step 3 Entity Linking - Heuristic Version
Uses string similarity and curated lists instead of Wikidata API.
"""

import json
import sys
import traceback
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

LINK_DIR = ROOT / "kg_artifacts" / "linking"
LINK_DIR.mkdir(parents=True, exist_ok=True)
log_file = LINK_DIR / "step3_heuristic_run.log"
log_file.write_text("STARTED\n", encoding="utf-8")

try:
    from src.kg.heuristic_linking import HeuristicEntityLinker
    from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef
    from rdflib.namespace import SKOS, PROV, XSD
    
    # Constants
    BASE_GRAPH_FILE = ROOT / "kg_artifacts" / "base_graph.ttl"
    ALIGNED_GRAPH_FILE = ROOT / "kg_artifacts" / "aligned_graph.ttl"
    AUTO_LINKS_FILE = LINK_DIR / "auto_links.jsonl"
    CANDIDATE_LINKS_FILE = LINK_DIR / "candidate_links.jsonl"
    REJECTED_LINKS_FILE = LINK_DIR / "rejected_links.jsonl"
    LINK_SUMMARY_FILE = LINK_DIR / "linking_summary.json"
    
    EX = Namespace("http://example.org/ai-kg/")
    WD = Namespace("http://www.wikidata.org/entity/")
    
    # Load base graph and extract entities
    print("[Step3-Heuristic] Loading base graph...")
    graph = Graph()
    with open(BASE_GRAPH_FILE, 'r', encoding='utf-8') as f:
        graph.parse(file=f, format="turtle")
    
    # Extract entities from graph
    entities: List[Dict[str, Any]] = []
    seen = set()
    
    for s, _, o in graph.triples((None, RDFS.label, None)):
        label = str(o)
        etype_obj = graph.value(s, EX.entityType)
        if etype_obj is None or (label, str(etype_obj)) in seen:
            continue
        seen.add((label, str(etype_obj)))
        
        context_obj = graph.value(s, SKOS.altLabel)
        entities.append({
            "entity_text": label,
            "entity_type": str(etype_obj),
            "sentence_context": str(context_obj) if context_obj else "",
            "local_uri": str(s),
        })
    
    print(f"[Step3-Heuristic] Found {len(entities)} unique entities")
    
    # Run heuristic linking
    linker = HeuristicEntityLinker()
    stats = linker.process_entities(entities)
    
    # Write results
    print("[Step3-Heuristic] Writing results...")
    
    def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    
    _write_jsonl(AUTO_LINKS_FILE, linker.auto_linked)
    _write_jsonl(CANDIDATE_LINKS_FILE, linker.candidates)
    _write_jsonl(REJECTED_LINKS_FILE, linker.rejected)
    
    # Update summary
    summary = {
        "total_unique_entities": stats["total_unique_entities"],
        "auto_linked": stats["auto_linked"],
        "candidate": stats["candidate"],
        "rejected": stats["rejected"],
        "linked_entities": stats["linked_entities"],
        "linked_percentage": stats["linked_percentage"],
        "method": "heuristic",
        "note": "Uses string similarity and curated entity lists, no Wikidata API"
    }
    
    LINK_SUMMARY_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    
    # Update aligned graph with pseudo-links
    print("[Step3-Heuristic] Updating aligned graph with pseudo-links...")
    
    for link in linker.auto_linked + linker.candidates:
        local_uri = URIRef(link.get("local_uri", ""))
        pseudo_uri = link.get("pseudo_uri", "")
        if pseudo_uri:
            graph.add((local_uri, OWL.sameAs, URIRef(pseudo_uri)))
    
    # Serialize to turtle and write to file
    turtle_content = graph.serialize(format="turtle")
    with open(ALIGNED_GRAPH_FILE, 'w', encoding='utf-8') as f:
        f.write(turtle_content)
    
    print(f"[Step3-Heuristic] Linked {stats['linked_entities']} entities ({stats['linked_percentage']}%)")
    
    log_file.write_text("SUCCESS\n" + json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

except Exception as e:
    log_file.write_text("ERROR\n" + traceback.format_exc(), encoding="utf-8")
    raise
