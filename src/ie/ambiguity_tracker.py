"""
Ambiguity Detection and Analysis
- Identify entity name collisions
- Track acronym ambiguities
- Document nested entity conflicts
"""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Any, Set

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def flag_ambiguities(entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze entities to find ambiguities.
    
    Args:
        entities: List of entity dictionaries
    
    Returns:
        Dictionary containing identified ambiguities
    """
    ambiguities = []
    
    # Group entities by text
    entities_by_text = defaultdict(list)
    for entity in entities:
        text = entity["entity_text"].strip().lower()
        entities_by_text[text].append(entity)
    
    # Identify name collisions (same text, different types or contexts)
    for entity_text, occurrences in entities_by_text.items():
        if len(occurrences) < 2:
            continue
        
        # Check if types differ
        types = set(e["entity_type"] for e in occurrences)
        if len(types) > 1:
            ambiguity = {
                "entity_text": entity_text,
                "ambiguity_type": "type_collision",
                "types_found": list(types),
                "occurrences": occurrences[:3],  # Show first 3 occurrences
                "count": len(occurrences),
                "notes": f"Entity '{entity_text}' appears with different types: {', '.join(types)}"
            }
            ambiguities.append(ambiguity)
        
        # Check if contexts are very different
        contexts = [e.get("sentence_context", "")[:100] for e in occurrences]
        if len(set(contexts)) > 1:
            # Check for specific patterns (e.g., "Paris" city vs "Paris" person)
            if entity_text.lower() == "paris":
                ambiguity = {
                    "entity_text": entity_text,
                    "ambiguity_type": "entity_name_collision",
                    "occurrences": occurrences[:3],
                    "count": len(occurrences),
                    "notes": "Potential ambiguity: 'Paris' could refer to city (GPE) or person (PERSON/ORG)"
                }
                ambiguities.append(ambiguity)
    
    # Identify acronym ambiguities
    acronyms = defaultdict(list)
    for entity in entities:
        text = entity["entity_text"].strip()
        # Simple heuristic: all uppercase, 2-4 chars
        if text.isupper() and 2 <= len(text) <= 4 and text not in ['AI', 'ML', 'DL', 'KG', 'NLP']:
            acronyms[text].append(entity)
    
    for acronym, occurrences in acronyms.items():
        if len(occurrences) >= 2:
            types = set(e["entity_type"] for e in occurrences)
            if len(types) > 1:
                ambiguity = {
                    "entity_text": acronym,
                    "ambiguity_type": "acronym_ambiguity",
                    "types_found": list(types),
                    "occurrences": occurrences[:3],
                    "count": len(occurrences),
                    "notes": f"Acronym '{acronym}' appears with types: {', '.join(types)}"
                }
                ambiguities.append(ambiguity)
    
    # Identify high-confidence vs low-confidence versions of same entity
    high_conf = [e for e in entities if e["confidence"] >= 0.85]
    low_conf = [e for e in entities if e["confidence"] < 0.75]
    
    low_conf_by_text = defaultdict(list)
    for e in low_conf:
        text = e["entity_text"].strip().lower()
        low_conf_by_text[text].append(e)
    
    for text, low_occs in low_conf_by_text.items():
        high_occs = [e for e in high_conf if e["entity_text"].strip().lower() == text]
        if high_occs and len(low_occs) >= 2:
            ambiguity = {
                "entity_text": text,
                "ambiguity_type": "confidence_variance",
                "low_confidence_occurrences": low_occs,
                "high_confidence_count": len(high_occs),
                "notes": f"Entity '{text}' has variable confidence across occurrences"
            }
            ambiguities.append(ambiguity)
    
    return {
        "total_ambiguities": len(ambiguities),
        "ambiguities": ambiguities
    }


def generate_ambiguity_report(entities_jsonl_file: str, 
                             output_json_file: str = "data/ambiguity_examples.json") -> None:
    """
    Generate a report of ambiguous entities.
    
    Args:
        entities_jsonl_file: Path to entities JSONL file
        output_json_file: Path to output ambiguity report JSON
    """
    Path(output_json_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Load entities
    entities = []
    try:
        with open(entities_jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        entities.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        logger.error(f"File not found: {entities_jsonl_file}")
        return
    
    if not entities:
        logger.warning("No entities found to analyze for ambiguities")
        return
    
    # Analyze ambiguities
    analysis = flag_ambiguities(entities)
    
    # Sort by count (descending) and keep top ambiguities
    ambiguities = analysis["ambiguities"]
    ambiguities.sort(key=lambda x: x.get("count", 1), reverse=True)
    analysis["ambiguities"] = ambiguities[:10]  # Keep top 10
    
    # Write report
    with open(output_json_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    
    # Log summary
    logger.info(f"\n{'='*60}")
    logger.info(f"Ambiguity Analysis Complete:")
    logger.info(f"  Total entities analyzed: {len(entities)}")
    logger.info(f"  Ambiguities found: {analysis['total_ambiguities']}")
    logger.info(f"\n  Top Ambiguities:")
    
    for i, amb in enumerate(ambiguities[:3], 1):
        logger.info(f"\n  {i}. {amb['entity_text']}")
        logger.info(f"     Type: {amb['ambiguity_type']}")
        logger.info(f"     Notes: {amb.get('notes', 'N/A')}")
        logger.info(f"     Occurrences: {amb.get('count', len(amb.get('occurrences', [])))}")
    
    logger.info(f"\n  Output: {output_json_file}")
    logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    generate_ambiguity_report("data/entities.jsonl")
