"""
Module 1 Expansion: Crawl remaining 5 seed URLs + apply entity filtering
Crawl: DFKI, MILA, PRAIRIE, ICML, ECAI
Then combine with existing data and apply post-processing filters
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.crawl.crawler import batch_crawl
from src.crawl.cleaning import batch_clean
from src.ie.ner import batch_ner
from src.ie.post_filter import filter_false_positives
from src.ie.ambiguity_tracker import generate_ambiguity_report
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def apply_filtering_to_entities(jsonl_file: str, output_file: str):
    """
    Apply post-processing filters to remove false positives.
    
    Args:
        jsonl_file: Input entities JSONL file
        output_file: Output filtered entities JSONL file
    """
    logger.info(f"Applying post-processing filters to {jsonl_file}...")
    
    # Load all entities
    entities = []
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                entities.append(json.loads(line))
    
    logger.info(f"Loaded {len(entities)} entities")
    
    # Filter false positives
    filtered_entities, dropped = filter_false_positives(entities)
    
    # Log dropped entities
    logger.info(f"\nDropped {len(dropped)} false positives:")
    for text, etype, reason in dropped[:10]:  # Show first 10
        logger.info(f"  - '{text}' ({etype}): {reason}")
    if len(dropped) > 10:
        logger.info(f"  ... and {len(dropped) - 10} more")
    
    # Write filtered entities
    with open(output_file, 'w', encoding='utf-8') as f:
        for entity in filtered_entities:
            f.write(json.dumps(entity, ensure_ascii=False) + "\n")
    
    logger.info(f"\nKept {len(filtered_entities)} valid entities")
    logger.info(f"Output: {output_file}")
    
    return filtered_entities, dropped


def main():
    """Run Module 1 expansion: crawl remaining URLs and filter entities."""
    
    print("\n" + "="*70)
    print("MODULE 1 EXPANSION: Crawl Remaining 5 Seed URLs")
    print("="*70 + "\n")
    
    # New seed URLs to crawl
    NEW_SEED_URLS = [
        "https://dfki.de/en",
        "https://mila.quebec/en",
        "https://prairie-institute.fr",
        "https://icml.cc",
        "https://ecai2024.eu",
    ]
    
    print("[1/5] Crawling remaining 5 seed URLs...")
    batch_crawl(NEW_SEED_URLS, "data/raw/crawl_output_batch2.jsonl")
    
    print("[2/5] Cleaning new crawled content...")
    batch_clean("data/raw/crawl_output_batch2.jsonl", "data/cleaned/cleaned_output_batch2.jsonl")
    
    print("[3/5] Running NER on new content...")
    batch_ner("data/cleaned/cleaned_output_batch2.jsonl",
              "data/entities_batch2.jsonl",
              "data/entities_batch2.csv")
    
    print("[4/5] Combining entities from both batches...")
    # Combine JSONL files
    combined_entities = []
    for jsonl_file in ["data/entities.jsonl", "data/entities_batch2.jsonl"]:
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    combined_entities.append(json.loads(line))
    
    combined_jsonl = "data/entities_all.jsonl"
    with open(combined_jsonl, 'w', encoding='utf-8') as f:
        for entity in combined_entities:
            f.write(json.dumps(entity, ensure_ascii=False) + "\n")
    
    logger.info(f"Combined {len(combined_entities)} entities from both batches")
    
    print("[5/5] Applying post-processing filters...")
    filtered_entities, dropped = apply_filtering_to_entities(combined_jsonl, "data/entities_final.jsonl")
    
    # Generate ambiguity report on filtered entities
    print("\nGenerating ambiguity analysis on filtered entities...")
    generate_ambiguity_report("data/entities_final.jsonl", "data/ambiguity_examples_final.json")
    
    # Summary statistics
    print("\n" + "="*70)
    print("MODULE 1 EXPANSION COMPLETE ✓")
    print("="*70)
    print(f"\nEntity Statistics:")
    print(f"  Batch 1 (3 URLs): 49 extracted")
    print(f"  Batch 2 (5 URLs): {len([e for e in combined_entities if e.get('source_url') not in ['https://inria.fr/en', 'https://ellis.eu', 'https://neurips.cc']])} extracted")
    print(f"  Combined Total: {len(combined_entities)}")
    print(f"  After Filtering: {len(filtered_entities)}")
    print(f"  False Positives Removed: {len(dropped)}")
    print(f"\nFiles:")
    print(f"  ✓ data/entities_final.jsonl (filtered entities)")
    print(f"  ✓ data/ambiguity_examples_final.json (ambiguity analysis)")
    print(f"\nReady for Module 2: KB Construction & Alignment")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
