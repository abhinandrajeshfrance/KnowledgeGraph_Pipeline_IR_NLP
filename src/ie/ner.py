"""
Named Entity Recognition (NER) Pipeline
- Load spaCy model with fallback
- Extract entities with confidence scores
- Support: PERSON, ORG, GPE, DATE, MISC, PRODUCT, WORK_OF_ART
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
import spacy
from spacy.language import Language

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_spacy_model(model_name: str = "en_core_web_trf") -> Optional[Language]:
    """
    Load spaCy model with fallback to smaller model if primary unavailable.
    
    Args:
        model_name: Primary model to load (usually transformer-based)
    
    Returns:
        Loaded spaCy Language model, or None if all attempts fail
    """
    models_to_try = [model_name, "en_core_web_sm", "en_core_web_md"]
    
    for model in models_to_try:
        try:
            nlp = spacy.load(model)
            logger.info(f"✓ Loaded spaCy model: {model}")
            return nlp
        except OSError:
            logger.warning(f"✗ Model {model} not available, trying fallback...")
            continue
    
    logger.error("✗ No spaCy models available. Please install one: python -m spacy download en_core_web_sm")
    return None


def compute_confidence(ent, nlp: Language) -> float:
    """
    Compute confidence score for an entity using heuristic-based scoring.
    
    Args:
        ent: spaCy Entity object
        nlp: spaCy Language model
    
    Returns:
        Confidence score (0.0 to 1.0)
    """
    # Heuristic confidence scoring
    confidence_map = {
        "PERSON": 0.90,
        "ORG": 0.85,
        "GPE": 0.90,
        "DATE": 0.95,
        "MISC": 0.70,
        "PRODUCT": 0.80,
        "WORK_OF_ART": 0.75,
    }
    
    base_conf = confidence_map.get(ent.label_, 0.70)
    
    # Adjust based on capitalization
    if ent.text[0].isupper():
        base_conf += 0.05
    
    # Adjust based on length (longer entities are often more specific)
    if len(ent.text.split()) > 2:
        base_conf += 0.03
    
    return min(base_conf, 1.0)


def run_ner_on_text(text: str, nlp: Language) -> List[Dict[str, Any]]:
    """
    Run NER on text and extract entities with context.
    
    Args:
        text: Text to process
        nlp: spaCy Language model
    
    Returns:
        List of extracted entities with metadata
    """
    if not nlp or not text:
        return []
    
    try:
        doc = nlp(text)
        entities = []
        
        for ent in doc.ents:
            # Get sentence context
            sent = ent.sent.text if ent.sent else text
            
            entity_dict = {
                "entity_text": ent.text,
                "entity_type": ent.label_,
                "confidence": compute_confidence(ent, nlp),
                "sentence_context": sent.strip(),
                "char_start": ent.start_char,
                "char_end": ent.end_char,
            }
            entities.append(entity_dict)
        
        return entities
    except Exception as e:
        logger.warning(f"NER processing failed: {e}")
        return []


def extract_entities_from_url(url: str, text: str, nlp: Language) -> List[Dict[str, Any]]:
    """
    Extract entities from a URL's text content.
    
    Args:
        url: Source URL
        text: Cleaned text content
        nlp: spaCy Language model
    
    Returns:
        List of entities with source URL
    """
    entities = run_ner_on_text(text, nlp)
    
    for ent in entities:
        ent["source_url"] = url
        ent["extraction_timestamp"] = datetime.utcnow().isoformat() + "Z"
    
    return entities


def batch_ner(cleaned_jsonl_file: str, 
              output_jsonl_file: str = "data/entities.jsonl",
              output_csv_file: str = "data/entities.csv") -> None:
    """
    Run NER on all cleaned documents.
    
    Args:
        cleaned_jsonl_file: Path to cleaned content JSONL
        output_jsonl_file: Path to output entities JSONL
        output_csv_file: Path to output entities CSV
    """
    Path(output_jsonl_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Load spaCy model
    nlp = load_spacy_model()
    if nlp is None:
        logger.error("Cannot proceed without spaCy model. Aborting.")
        return
    
    stats = {
        "total_urls": 0,
        "total_entities": 0,
        "per_type": {},
        "confidence_stats": {"min": 1.0, "max": 0.0, "avg": 0.0},
    }
    
    all_entities = []
    confidence_scores = []
    
    # Load cleaned data
    try:
        with open(cleaned_jsonl_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(f"Skipping malformed JSON at line {line_num}")
                    continue
                
                url = record.get("url", "unknown")
                text = record.get("cleaned_text", "")
                
                if not text:
                    continue
                
                stats["total_urls"] += 1
                
                # Extract entities
                entities = extract_entities_from_url(url, text, nlp)
                
                for entity in entities:
                    all_entities.append(entity)
                    stats["total_entities"] += 1
                    
                    # Update statistics
                    etype = entity["entity_type"]
                    stats["per_type"][etype] = stats["per_type"].get(etype, 0) + 1
                    
                    conf = entity["confidence"]
                    confidence_scores.append(conf)
                
                logger.info(f"✓ Processed URL {stats['total_urls']}: {url} ({len(entities)} entities)")
    
    except FileNotFoundError:
        logger.error(f"File not found: {cleaned_jsonl_file}")
        return
    
    # Compute confidence statistics
    if confidence_scores:
        stats["confidence_stats"]["min"] = min(confidence_scores)
        stats["confidence_stats"]["max"] = max(confidence_scores)
        stats["confidence_stats"]["avg"] = sum(confidence_scores) / len(confidence_scores)
    
    # Write JSONL output
    with open(output_jsonl_file, 'w', encoding='utf-8') as f:
        for entity in all_entities:
            f.write(json.dumps(entity, ensure_ascii=False) + "\n")
    
    # Write CSV output
    df = pd.DataFrame(all_entities)
    if not df.empty:
        # Select key columns for CSV
        csv_columns = ["entity_text", "entity_type", "source_url", "confidence", "sentence_context"]
        df_csv = df[[col for col in csv_columns if col in df.columns]]
        df_csv.to_csv(output_csv_file, index=False, encoding='utf-8')
    
    # Log statistics
    logger.info(f"\n{'='*60}")
    logger.info(f"NER Complete:")
    logger.info(f"  Total URLs processed: {stats['total_urls']}")
    logger.info(f"  Total entities extracted: {stats['total_entities']}")
    logger.info(f"\n  Entities by type:")
    for etype, count in sorted(stats["per_type"].items()):
        logger.info(f"    {etype}: {count}")
    logger.info(f"\n  Confidence scores:")
    logger.info(f"    Min: {stats['confidence_stats']['min']:.3f}")
    logger.info(f"    Max: {stats['confidence_stats']['max']:.3f}")
    logger.info(f"    Avg: {stats['confidence_stats']['avg']:.3f}")
    logger.info(f"\n  Output JSONL: {output_jsonl_file}")
    logger.info(f"  Output CSV:  {output_csv_file}")
    logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    batch_ner("data/cleaned/cleaned_output.jsonl")
