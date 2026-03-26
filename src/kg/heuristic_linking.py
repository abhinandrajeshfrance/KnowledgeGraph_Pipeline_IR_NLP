#!/usr/bin/env python3
"""
Heuristic entity linking using string similarity and curated entity lists.
Avoids Wikidata API rate limiting by using internal pseudo-URIs.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set
from collections import Counter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Curated entity databases
KNOWN_ORGANIZATIONS = {
    "Inria": "ex:org/Inria",
    "INRIA": "ex:org/Inria",
    "ELLIS": "ex:org/ELLIS",
    "CNRS": "ex:org/CNRS",
    "PRAIRIE": "ex:org/PRAIRIE",
    "CEA": "ex:org/CEA",
    "Sorbonne University": "ex:org/Sorbonne",
    "MIT": "ex:org/MIT",
    "Stanford": "ex:org/Stanford",
    "Oxford": "ex:org/Oxford",
    "Cambridge": "ex:org/Cambridge",
    "Harvard": "ex:org/Harvard",
    "UC Berkeley": "ex:org/Berkeley",
    "CMU": "ex:org/CMU",
    "Google": "ex:org/Google",
    "Microsoft": "ex:org/Microsoft",
    "Facebook": "ex:org/Facebook",
    "Meta": "ex:org/Meta",
    "OpenAI": "ex:org/OpenAI",
    "DeepMind": "ex:org/DeepMind",
    "Stanford Research": "ex:org/Stanford",
    "University of Paris": "ex:org/Paris",
}

KNOWN_CONFERENCES = {
    "NeurIPS": "ex:conf/NeurIPS",
    "ICML": "ex:conf/ICML",
    "ICLR": "ex:conf/ICLR",
    "AAAI": "ex:conf/AAAI",
    "IJCAI": "ex:conf/IJCAI",
    "ACL": "ex:conf/ACL",
    "NIPS": "ex:conf/NeurIPS",
    "ECCV": "ex:conf/ECCV",
    "ICCV": "ex:conf/ICCV",
    "CVPR": "ex:conf/CVPR",
    "EMNLP": "ex:conf/EMNLP",
    "KDD": "ex:conf/KDD",
    "SIGMOD": "ex:conf/SIGMOD",
    "WWW": "ex:conf/WWW",
}

KNOWN_LOCATIONS = {
    "France": "ex:loc/France",
    "Germany": "ex:loc/Germany",
    "UK": "ex:loc/UK",
    "United Kingdom": "ex:loc/UK",
    "USA": "ex:loc/USA",
    "United States": "ex:loc/USA",
    "Europe": "ex:loc/Europe",
    "Paris": "ex:loc/Paris",
    "Berlin": "ex:loc/Berlin",
    "London": "ex:loc/London",
    "Amsterdam": "ex:loc/Amsterdam",
    "Montreal": "ex:loc/Montreal",
    "Toronto": "ex:loc/Toronto",
    "Vancouver": "ex:loc/Vancouver",
    "San Francisco": "ex:loc/SanFrancisco",
    "New York": "ex:loc/NewYork",
    "Boston": "ex:loc/Boston",
    "Switzerland": "ex:loc/Switzerland",
    "Spain": "ex:loc/Spain",
    "Italy": "ex:loc/Italy",
    "Japan": "ex:loc/Japan",
    "China": "ex:loc/China",
    "Australia": "ex:loc/Australia",
}

ORG_KEYWORDS = {
    "institute", "university", "lab", "laboratory", "center", "centre",
    "department", "company", "organization", "corps", "group", "team",
    "research", "school", "faculty", "academy", "foundation", "corporation",
}

PERSON_TITLES = {
    "professor", "prof", "dr", "researcher", "scientist", "author",
    "engineer", "architect", "designer", "inventor", "director",
}


def _normalize_text(text: str) -> str:
    """Normalize text for matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    ascii_text = re.sub(r"[^A-Za-z0-9\s]", " ", ascii_text).lower().strip()
    return re.sub(r"\s+", " ", ascii_text)


def _levenshtein_ratio(a: str, b: str) -> float:
    """Calculate Levenshtein similarity ratio."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            cur = dp[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = cur
    dist = dp[n]
    return 1.0 - (dist / max(m, n))


def _token_overlap(a: str, b: str) -> float:
    """Calculate token-based overlap."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _string_similarity(a: str, b: str) -> float:
    """Combined string similarity."""
    norm_a = _normalize_text(a)
    norm_b = _normalize_text(b)
    
    if norm_a == norm_b:
        return 1.0
    if norm_a in norm_b or norm_b in norm_a:
        return 0.85
    
    lev = _levenshtein_ratio(norm_a, norm_b)
    tok = _token_overlap(norm_a, norm_b)
    return 0.6 * lev + 0.4 * tok


def _infer_org_match(text: str) -> bool:
    """Rule-based: check if text looks like an organization."""
    norm = _normalize_text(text)
    words = norm.split()
    
    # Check for org keywords
    if any(kw in norm for kw in ORG_KEYWORDS):
        return True
    
    # Check for acronyms (all caps, 2-5 chars)
    if all(c.isupper() or c == "-" for c in text if c.isalpha()):
        if 2 <= sum(1 for c in text if c.isalpha()) <= 5:
            return True
    
    return False


def _infer_person_match(text: str) -> bool:
    """Rule-based: check if text looks like a person name."""
    words = text.split()
    
    # Need at least 2 words with capitals
    if len(words) < 2:
        return False
    
    cap_words = [w for w in words if w and w[0].isupper()]
    return len(cap_words) >= 2


def _infer_location_match(text: str) -> bool:
    """Rule-based: check if text looks like a location."""
    norm = _normalize_text(text)
    # Single capitalized word (common for cities/countries)
    words = text.split()
    if len(words) == 1 and text[0].isupper():
        return True
    return False


class HeuristicEntityLinker:
    """Heuristic entity linking without Wikidata."""
    
    def __init__(self):
        self.curated_orgs = KNOWN_ORGANIZATIONS
        self.curated_confs = KNOWN_CONFERENCES
        self.curated_locs = KNOWN_LOCATIONS
        self.auto_linked: List[Dict[str, Any]] = []
        self.candidates: List[Dict[str, Any]] = []
        self.rejected: List[Dict[str, Any]] = []
        self.seen_matches: Set[str] = set()  # Track duplicates
    
    def link_entity(self, entity_text: str, entity_type: str, context: str = "") -> Dict[str, Any]:
        """
        Attempt to link a single entity using heuristics.
        
        Returns:
            Dict with linking result (auto, candidate, or rejected)
        """
        entity_text = entity_text.strip()
        norm_text = _normalize_text(entity_text)
        
        # Skip if already linked
        key = (norm_text, entity_type)
        if key in self.seen_matches:
            return {"status": "duplicate"}
        
        result = {
            "entity_text": entity_text,
            "entity_type": entity_type,
            "status": "rejected",
            "score": 0.0,
        }
        
        # Try curated matches first
        matched_uri, match_type, score = self._try_curated_match(
            entity_text, entity_type
        )
        
        if score >= 0.85:
            result.update({
                "status": "auto_linked",
                "pseudo_uri": matched_uri,
                "match_type": match_type,
                "score": score,
            })
            self.seen_matches.add(key)
            return result
        
        # Try type-based heuristics
        if entity_type == "ORG":
            if _infer_org_match(entity_text):
                uri = self._create_pseudo_uri("org", entity_text)
                if score < 0.6:
                    score = 0.72  # Heuristic boost
                result.update({
                    "status": "candidate",
                    "pseudo_uri": uri,
                    "match_type": "type_inference",
                    "score": score,
                    "reasoning": "Inferred ORG from keywords",
                })
                self.seen_matches.add(key)
                return result
        
        elif entity_type == "PERSON":
            if _infer_person_match(entity_text):
                uri = self._create_pseudo_uri("person", entity_text)
                if score < 0.6:
                    score = 0.70
                result.update({
                    "status": "candidate",
                    "pseudo_uri": uri,
                    "match_type": "name_pattern",
                    "score": score,
                    "reasoning": "Inferred PERSON from name pattern",
                })
                self.seen_matches.add(key)
                return result
        
        elif entity_type in {"GPE", "LOC"}:
            if _infer_location_match(entity_text):
                uri = self._create_pseudo_uri("location", entity_text)
                if score < 0.6:
                    score = 0.68
                result.update({
                    "status": "candidate",
                    "pseudo_uri": uri,
                    "match_type": "location_pattern",
                    "score": score,
                    "reasoning": "Inferred LOCATION from pattern",
                })
                self.seen_matches.add(key)
                return result
        
        # No match
        result["reason"] = "no_heuristic_match"
        return result
    
    def _try_curated_match(self, text: str, entity_type: str) -> Tuple[str, str, float]:
        """Try to match against curated entity lists."""
        candidates_dict: Dict[str, Tuple[str, float]] = {}
        
        # ORG matches
        if entity_type == "ORG":
            for known, uri in list(self.curated_orgs.items()) + list(self.curated_confs.items()):
                sim = _string_similarity(text, known)
                if sim > 0.6:
                    candidates_dict[uri] = (known, sim)
        
        # PERSON matches (less curated, more heuristic)
        elif entity_type == "PERSON":
            pass  # No curated person list, handle via name pattern
        
        # Location matches
        elif entity_type in {"GPE", "LOC"}:
            for known, uri in self.curated_locs.items():
                sim = _string_similarity(text, known)
                if sim > 0.6:
                    candidates_dict[uri] = (known, sim)
        
        # Return best match
        if candidates_dict:
            best_uri = max(candidates_dict, key=lambda u: candidates_dict[u][1])
            known, score = candidates_dict[best_uri]
            return best_uri, "curated_match", score
        
        return "", "", 0.0
    
    def _create_pseudo_uri(self, entity_class: str, text: str) -> str:
        """Create a consistent pseudo-URI for an entity."""
        norm = _normalize_text(text).replace(" ", "-")[:40]
        return f"ex:entity/{entity_class}/{norm}"
    
    def process_entities(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process all entities and return statistics."""
        print(f"[Heuristic Linking] Processing {len(entities)} entities...")
        
        for i, ent in enumerate(entities):
            if i % 10 == 0:
                print(f"  Progress: {i}/{len(entities)} "
                      f"(auto: {len(self.auto_linked)}, "
                      f"cand: {len(self.candidates)}, "
                      f"rej: {len(self.rejected)})")
            
            result = self.link_entity(
                ent.get("entity_text", ""),
                ent.get("entity_type", ""),
                ent.get("sentence_context", ""),
            )
            
            if result["status"] == "duplicate":
                continue
            
            # Attach original entity info
            result["local_uri"] = f"ex:entity/{_normalize_text(ent.get('entity_text', '')).replace(' ', '-')}"
            
            if result["status"] == "auto_linked":
                self.auto_linked.append(result)
            elif result["status"] == "candidate":
                self.candidates.append(result)
            else:
                self.rejected.append(result)
        
        total = len(self.auto_linked) + len(self.candidates) + len(self.rejected)
        linked = len(self.auto_linked) + len(self.candidates)
        linked_pct = (linked / total * 100) if total > 0 else 0.0
        
        return {
            "total_unique_entities": total,
            "auto_linked": len(self.auto_linked),
            "candidate": len(self.candidates),
            "rejected": len(self.rejected),
            "linked_entities": linked,
            "linked_percentage": round(linked_pct, 2),
        }


if __name__ == "__main__":
    # Quick test
    linker = HeuristicEntityLinker()
    
    test_orgs = [
        "Inria",
        "CNRS",
        "National Institute for Research",
        "Research Institute",
        "MIT",
    ]
    
    test_persons = [
        "John Smith",
        "Peter Eisenman",
        "Alice Johnson",
    ]
    
    test_locs = [
        "Paris",
        "Amsterdam",
        "France",
        "Germany",
    ]
    
    print("[Test] ORGs:")
    for org in test_orgs:
        result = linker.link_entity(org, "ORG")
        print(f"  {org}: {result['status']} (score: {result.get('score', 0)})")
    
    print("\n[Test] PERSONs:")
    for person in test_persons:
        result = linker.link_entity(person, "PERSON")
        print(f"  {person}: {result['status']} (score: {result.get('score', 0)})")
    
    print("\n[Test] LOCs:")
    for loc in test_locs:
        result = linker.link_entity(loc, "GPE")
        print(f"  {loc}: {result['status']} (score: {result.get('score', 0)})")
