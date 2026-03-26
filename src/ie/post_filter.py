"""
Entity Post-Processing: Remove False Positives
- Filter common non-English phrases (French, etc.)
- Filter PERSON entities without capitalized proper nouns
- Drop entities with very low confidence
"""

import re
from typing import List, Dict, Any

# Common French stopwords/phrases that shouldn't be entities
FRENCH_PHRASES = {
    'au cœur', 'au coeur', 'a propos', 'à propos', 'd\'orchestre', 'du pôle',
    'la data', 'au pôle', 'en particulier', 'par ailleurs', 'en effet',
    'de plus', 'selon', 'ainsi', 'donc', 'or', 'mais', 'et', 'ou', 'que',
    'ce qui', 'qui est', 'où', 'quand', 'comment', 'pourquoi'
}

# Common false-positive patterns
FALSE_POSITIVE_PATTERNS = [
    r'^(the|a|an|for|with|from|in|on|at|to|by|about|and|or|but)\s',  # Leading articles/prepositions
    r'\s(of|and|or|the)\s',  # Mid-sentence connectors only
    r'^\d+(\s|$)',  # Bare numbers
    r'^[\'\"]+',  # Quote characters
]

# Generic role/group terms that should not be kept as PERSON entities.
PERSON_BLACKLIST_TOKENS = {
    "fellows",
    "scholars",
    "masterclasses",
    "researchers",
    "students",
}

PERSON_INVALID_TAIL_TOKENS = {"le", "la", "les"}


def is_valid_proper_noun(text: str) -> bool:
    """
    Check if text looks like a proper noun (contains capitalized words).
    
    Args:
        text: Entity text
    
    Returns:
        True if text contains at least one capitalized word or is all-caps acronym
    """
    words = text.split()
    
    # All uppercase = likely an acronym (valid)
    if all(w.isupper() for w in words if len(w) > 1):
        return True
    
    # Has at least one capitalized word
    if any(w[0].isupper() for w in words if w and w[0].isalpha()):
        return True
    
    return False


def is_common_phrase(text: str) -> bool:
    """
    Check if text is a common non-entity phrase.
    
    Args:
        text: Entity text
    
    Returns:
        True if text is likely a common phrase, not a named entity
    """
    lower_text = text.lower().strip()
    
    # Direct French phrase match
    if lower_text in FRENCH_PHRASES:
        return True
    
    # Check patterns
    for pattern in FALSE_POSITIVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False


def is_valid_person_entity(text: str) -> bool:
    """
    PERSON entities must contain at least one proper noun.
    
    Args:
        text: Entity text
    
    Returns:
        True if entity looks like a valid person name
    """
    words = [w.strip(".,;:()[]{}\"'") for w in text.split() if w.strip()]
    if not words:
        return False

    lowered_words = {w.lower() for w in words}
    if lowered_words & PERSON_BLACKLIST_TOKENS:
        return False

    # UI cookie text artifacts often appear as "X Le/La/Les".
    if len(words) >= 2 and words[-1].lower() in PERSON_INVALID_TAIL_TOKENS:
        return False

    # Keep PERSON only if it contains at least one token that starts with a
    # capital letter and is longer than 3 characters.
    has_name_like_token = any(
        len(w) > 3 and w[0].isupper() for w in words if w and w[0].isalpha()
    )
    if not has_name_like_token:
        return False

    # Retain previous capitalization guard as a final check.
    return is_valid_proper_noun(text)


def filter_false_positives(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove false-positive entities.
    
    Args:
        entities: List of entity dictionaries
    
    Returns:
        Filtered list of entities
    """
    filtered = []
    dropped = []
    
    for entity in entities:
        text = entity.get("entity_text", "").strip()
        etype = entity.get("entity_type", "")
        confidence = entity.get("confidence", 0.0)

        # Drop crawl artifact entity 'ai' (case-insensitive exact match).
        if text.lower() == "ai":
            dropped.append((text, etype, "ai_artifact"))
            continue
        
        # Drop very low confidence
        if confidence < 0.65:
            dropped.append((text, etype, "low_confidence"))
            continue
        
        # Drop common phrases
        if is_common_phrase(text):
            dropped.append((text, etype, "common_phrase"))
            continue
        
        # Drop PERSON entities without proper nouns
        if etype == "PERSON" and not is_valid_person_entity(text):
            dropped.append((text, etype, "invalid_person_name"))
            continue
        
        filtered.append(entity)
    
    return filtered, dropped


if __name__ == "__main__":
    # Test
    test_entities = [
        {"entity_text": "Au cœur", "entity_type": "PERSON", "confidence": 0.95},
        {"entity_text": "Inria", "entity_type": "ORG", "confidence": 0.93},
        {"entity_text": "Marie Curie", "entity_type": "PERSON", "confidence": 0.92},
        {"entity_text": "ELLIS Fellows", "entity_type": "PERSON", "confidence": 0.95},
        {"entity_text": "ai", "entity_type": "ORG", "confidence": 0.90},
        {"entity_text": "low conf stuff", "entity_type": "MISC", "confidence": 0.55},
    ]
    
    filtered, dropped = filter_false_positives(test_entities)
    print(f"Kept: {len(filtered)}, Dropped: {len(dropped)}")
    for t, e, r in dropped:
        print(f"  Dropped: '{t}' ({e}) - reason: {r}")
