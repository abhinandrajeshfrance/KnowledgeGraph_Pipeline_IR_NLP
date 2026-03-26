"""
Module 1 Main Orchestrator
Runs: Crawl -> Clean -> NER -> Ambiguity Tracking

Usage:
    python src/crawl/run_module1.py
"""

import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.crawl.crawler import batch_crawl
from src.crawl.cleaning import batch_clean
from src.ie.ner import batch_ner
from src.ie.ambiguity_tracker import generate_ambiguity_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run full Module 1 pipeline."""
    
    # Seed URLs for crawling
    SEED_URLS = [
        "https://inria.fr/en",
        "https://dfki.de/en",
        "https://ellis.eu",
        "https://mila.quebec/en",
        "https://prairie-institute.fr/",
        "https://neurips.cc",
        "https://icml.cc",
        "https://ecai2024.eu",
    ]
    
    print("\n" + "="*70)
    print("MODULE 1: Web Crawling, Cleaning & Named Entity Recognition")
    print("Domain: European AI Research Ecosystem")
    print("="*70 + "\n")
    
    # Step 1: Crawl
    print("[1/4] CRAWLING seed URLs...")
    print(f"      URLs to crawl: {len(SEED_URLS)}")
    batch_crawl(SEED_URLS, "data/raw/crawl_output.jsonl")
    
    # Step 2: Clean
    print("[2/4] CLEANING crawled content...")
    batch_clean("data/raw/crawl_output.jsonl", "data/cleaned/cleaned_output.jsonl")
    
    # Step 3: NER
    print("[3/4] Running NAMED ENTITY RECOGNITION...")
    batch_ner("data/cleaned/cleaned_output.jsonl", 
              "data/entities.jsonl",
              "data/entities.csv")
    
    # Step 4: Ambiguity Tracking
    print("[4/4] Analyzing ENTITY AMBIGUITIES...")
    generate_ambiguity_report("data/entities.jsonl", "data/ambiguity_examples.json")
    
    print("\n" + "="*70)
    print("✓ MODULE 1 COMPLETE!")
    print("="*70)
    print("\nOutput Files:")
    print("  1. data/raw/crawl_output.jsonl       (raw fetch results)")
    print("  2. data/cleaned/cleaned_output.jsonl (cleaned text)")
    print("  3. data/entities.jsonl               (entities with confidence)")
    print("  4. data/entities.csv                 (entities in CSV format)")
    print("  5. data/ambiguity_examples.json      (identified ambiguities)")
    print("\nNext Steps:")
    print("  - Review ambiguities in data/ambiguity_examples.json")
    print("  - Proceed to Module 2 (KB Construction & Alignment)")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
