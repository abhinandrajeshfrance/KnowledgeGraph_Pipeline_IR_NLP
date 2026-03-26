#!/usr/bin/env python3
"""
Offline entity linking improvement using heuristics and pattern matching.
This avoids hitting Wikidata rate limits by working with cached data only.
"""

import json
import re
import unicodedata
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any, List, Tuple
import sys

# Get the workspace root directory
workspace_root = Path(__file__).resolve().parent
KG_DIR = workspace_root / "kg_artifacts"
LINK_DIR = KG_DIR / "linking"
DATA_DIR = workspace_root / "data"

print(f"[Debug] Workspace root: {workspace_root}")
print(f"[Debug] KG dir: {KG_DIR}")
print(f"[Debug] Link dir: {LINK_DIR}")

# Load existing auto_links, candidates, and rejected
auto_links_existing = []
candidates_existing = []
rejected_existing = []

print(f"[Debug] Looking for backup files in: {LINK_DIR / 'linking.bak'}")

if (LINK_DIR / "linking.bak" / "auto_links.jsonl").exists():
    print(f"[Debug] Found auto_links.jsonl")
    with open(str(LINK_DIR / "linking.bak" / "auto_links.jsonl")) as f:
        lines = f.readlines()
        print(f"[Debug] Read {len(lines)} lines from auto_links.jsonl")
        for i, line in enumerate(lines):
            if line.strip():
                try:
                    auto_links_existing.append(json.loads(line))
                except Exception as e:
                    print(f"[Debug] Error parsing line {i}: {e}")
else:
    print(f"[Debug] auto_links.jsonl not found at {LINK_DIR / 'linking.bak' / 'auto_links.jsonl'}")

if (LINK_DIR / "linking.bak" / "candidate_links.jsonl").exists():
    with open(str(LINK_DIR / "linking.bak" / "candidate_links.jsonl")) as f:
        for line in f:
            if line.strip():
                candidates_existing.append(json.loads(line))

if (LINK_DIR / "linking.bak" / "rejected_links.jsonl").exists():
    print(f"[Debug] Found rejected_links.jsonl")
    with open(str(LINK_DIR / "linking.bak" / "rejected_links.jsonl")) as f:
        lines = f.readlines()
        print(f"[Debug] Read {len(lines)} lines from rejected_links.jsonl")
        for i, line in enumerate(lines):
            if line.strip():
                try:
                    rejected_existing.append(json.loads(line))
                except Exception as e:
                    print(f"[Debug] Error parsing line {i}: {e}")
else:
    print(f"[Debug] rejected_links.jsonl not found at {LINK_DIR / 'linking.bak' / 'rejected_links.jsonl'}")


# Define important entities we should try to link
IMPORTANT_ORG_NAMES = {
    "National Institute for Research", 
    "Inria", 
    "INRIA",
    "Research Institute",
    "University",
}

IMPORTANT_PERSON_NAMES = {
    "Tiffany Chalier",
    "Peter Eisenman", 
    "John Smith",
    "Jane Doe",
}

IMPORTANT_LOCATIONS = {
    "Europe", "Paris", "France", "Amsterdam", "New York", "USA", 
    "United States", "United Kingdom", "Germany", "Spain", "Italy",
}


def _normalize_text(text: str) -> str:
    """Normalize text for matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return ascii_text.lower().strip()


def _score_rejection(rejection: Dict[str, Any]) -> float:
    """
    Re-score rejected entities using heuristics.
    Returns improved score if entity should be promoted.
    """
    entity_text = rejection.get("entity_text", "").strip()
    entity_type = rejection.get("entity_type", "")
    reason = rejection.get("reason", "")
    
    # Don't re-score query errors (Wikidata rate limit)
    if "query_error" in reason:
        return 0.0
    
    norm_text = _normalize_text(entity_text)
    
    # Check if this is an important entity
    if entity_type == "ORG":
        for org_pattern in IMPORTANT_ORG_NAMES:
            if _normalize_text(org_pattern) in norm_text or norm_text in _normalize_text(org_pattern):
                return 0.75  # Promote important orgs to candidate range
    
    if entity_type == "PERSON":
        # Check if it looks like a person name (has at least 2 parts)
        parts = entity_text.split()
        if len(parts) >= 2:
            # Check if both parts are capitalized (likely a person name)
            if all(p[0].isupper() for p in parts if p):
                return 0.70
    
    if entity_type in {"GPE", "LOC"}:
        for loc in IMPORTANT_LOCATIONS:
            if _normalize_text(loc) == norm_text:
                return 0.72
    
    return 0.0


def _improve_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Boost candidate scores for likely matches."""
    for cand in candidates:
        entity_text = cand.get("entity_text", "").strip()
        entity_type = cand.get("entity_type", "")
        matched_text = cand.get("matched_text", "").strip()
        score = float(cand.get("score", 0.0))
        
        # Boost score if matched_via is rdfs:label (more reliable)
        if cand.get("matched_via") == "rdfs:label" and score > 0.65:
            score = min(0.90, score + 0.08)
        
        # Boost if it's an obvious match
        if _normalize_text(entity_text) == _normalize_text(matched_text):
            score = min(0.97, score + 0.15)
        
        cand["score"] = round(score, 4)
    
    return candidates


print("[Offline Linking] Loading existing results...")
print(f"  - Auto-linked: {len(auto_links_existing)}")
print(f"  - Candidates: {len(candidates_existing)}")
print(f"  - Rejected: {len(rejected_existing)}")

# Process rejections to promote strong candidates
print("[Offline Linking] Re-scoring {0} rejected entities using heuristics...".format(len(rejected_existing)))

auto_links = auto_links_existing.copy()
candidates = _improve_candidates(candidates_existing.copy())
rejected = []

promoted_count = 0
for rejection in rejected_existing:
    improved_score = _score_rejection(rejection)
    
    if improved_score >= 0.85:
        # Promote to auto-linked (but without Wikidata QID)
        # For now, keep in candidates
        new_entry = {
            **rejection,
            "score": improved_score,
            "status": "candidate",
            "reason": "heuristic_match"
        }
        candidates.append(new_entry)
        promoted_count += 1
    elif improved_score >= 0.60:
        # Keep in candidate range
        new_entry = {
            **rejection,
            "score": improved_score,
            "status": "candidate",
            "reason": "heuristic_match"
        }
        candidates.append(new_entry)
        promoted_count += 1
    else:
        # Keep rejected
        rejected.append(rejection)

print(f"[Offline Linking] Promoted {promoted_count} entities to candidate range")

# Update summary
total_entities = len(auto_links) + len(candidates) + len(rejected)
summary = {
    "total_unique_entities": total_entities,
    "auto_linked": len(auto_links),
    "candidate": len(candidates),
    "rejected": len(rejected),
    "linked_percentage": round((len(auto_links) / total_entities) * 100, 2) if total_entities > 0 else 0.0,
    "auto_threshold": 0.85,
    "candidate_range": [0.60, 0.85],
    "notes": "Enhanced with heuristic re-scoring due to Wikidata rate limiting"
}

print(f"\n[Offline Linking] Final Results:")
print(f"  - Auto-linked: {summary['auto_linked']}")
print(f"  - Candidates: {summary['candidate']}")
print(f"  - Rejected: {summary['rejected']}")
print(f"  - Linked %: {summary['linked_percentage']}%")

# Write results
print(f"\n[Offline Linking] Writing results...")
with open(LINK_DIR / "auto_links.jsonl", 'w') as f:
    for item in auto_links:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

with open(LINK_DIR / "candidate_links.jsonl", 'w') as f:
    for item in candidates:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

with open(LINK_DIR / "rejected_links.jsonl", 'w') as f:
    for item in rejected:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

with open(LINK_DIR / "linking_summary.json", 'w') as f:
    f.write(json.dumps(summary, indent=2))

print("[Offline Linking] Done!")
