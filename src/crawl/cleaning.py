"""
Cleaning Pipeline for Web Content
- Normalize whitespace
- Filter by content length
- Deduplicate by hash
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Dict, Any, Optional

import trafilatura

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIN_CONTENT_LENGTH = 80  # words
STOPWORD_RATIO_THRESHOLD = 0.90

# Common English stopwords
STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has',
    'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
    'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
    'we', 'they', 'what', 'who', 'which', 'where', 'when', 'why', 'how'
}


def normalize_text(text: str) -> str:
    """
    Normalize text: lowercase, collapse whitespace, remove special chars.
    
    Args:
        text: Raw text
    
    Returns:
        Normalized text
    """
    # Collapse multiple spaces/newlines
    text = re.sub(r'\s+', ' ', text)
    
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    
    # Remove email addresses
    text = re.sub(r'\S+@\S+', '', text)
    
    # Remove phone numbers
    text = re.sub(r'[\+]?[(]?[0-9]{1,4}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,9}', '', text)
    
    # Keep only printable ASCII + common diacritics
    text = ''.join(c for c in text if ord(c) < 128 or ord(c) >= 192)
    
    return text.strip()


def word_count(text: str) -> int:
    """Count number of words in text."""
    return len(text.split())


def is_useful_content(text: str, min_words: int = MIN_CONTENT_LENGTH) -> tuple[bool, Optional[str]]:
    """
    Check if content is useful (not boilerplate, sufficient length).
    
    Args:
        text: Cleaned text
        min_words: Minimum word count threshold
    
    Returns:
        (is_useful: bool, filter_reason: str or None)
    """
    if not text:
        return False, "empty_content"
    
    word_count_val = word_count(text)
    if word_count_val < min_words:
        return False, f"too_short ({word_count_val} words)"
    
    # Check stopword ratio
    words = text.lower().split()
    stopword_count = sum(1 for w in words if w in STOPWORDS)
    stopword_ratio = stopword_count / len(words) if words else 0
    
    if stopword_ratio > STOPWORD_RATIO_THRESHOLD:
        return False, "too_many_stopwords"
    
    return True, None


def text_hash(text: str) -> str:
    """Compute SHA-256 hash of text for deduplication."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def load_raw_crawl(jsonl_file: str) -> Iterator[dict]:
    """
    Load raw crawl output from JSONL file.
    
    Args:
        jsonl_file: Path to raw crawl JSONL
    
    Yields:
        Dictionary for each crawl record
    """
    try:
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Skipping malformed JSON line: {e}")
    except FileNotFoundError:
        logger.error(f"File not found: {jsonl_file}")


def extract_main_text_from_html(html: str) -> Optional[str]:
    """
    Extract main content from HTML using trafilatura.
    
    Args:
        html: Raw HTML content
    
    Returns:
        Cleaned text or None if extraction fails
    """
    try:
        # Try with balanced settings first,then fallback to include_tables
        text = trafilatura.extract(html, include_comments=False, favor_precision=False)
        if not text or len(text.split()) < 50:
            # Fallback: try with tables included
            text = trafilatura.extract(html, include_comments=False, tables=True, favor_recall=True)
        return text
    except Exception as e:
        logger.warning(f"Trafilatura extraction failed: {e}")
        return None


def deduplicat_by_hash(records: List[dict]) -> List[dict]:
    """
    Remove duplicate records based on text hash.
    
    Args:
        records: List of cleaned records
    
    Returns:
        List with duplicates removed (keeps first occurrence)
    """
    seen_hashes = set()
    unique_records = []
    
    for record in records:
        text = record.get('cleaned_text', '')
        if text:
            h = text_hash(text)
            if h not in seen_hashes:
                seen_hashes.add(h)
                unique_records.append(record)
        else:
            unique_records.append(record)
    
    return unique_records


def batch_clean(raw_jsonl_file: str, output_jsonl_file: str = "data/cleaned/cleaned_output.jsonl") -> None:
    """
    Clean a batch of raw crawl output.
    
    Args:
        raw_jsonl_file: Path to raw crawl JSONL
        output_jsonl_file: Path to output cleaned JSONL
    """
    Path(output_jsonl_file).parent.mkdir(parents=True, exist_ok=True)
    
    stats = {
        "total": 0,
        "kept": 0,
        "filtered": 0,
        "duplicates": 0,
        "avg_text_length": 0,
    }
    
    # First pass: load and clean all records
    all_records = []
    for raw_record in load_raw_crawl(raw_jsonl_file):
        stats["total"] += 1
        
        if raw_record.get("error"):
            logger.warning(f"Skipping failed crawl: {raw_record['url']}")
            continue
        
        # Extract main text
        html = raw_record.get("raw_html", "")
        if not html:
            # We don't have raw HTML in our current crawler, so we skip this step
            cleaned_text = None
        else:
            cleaned_text = extract_main_text_from_html(html)
        
        filter_reason = None
        if not cleaned_text:
            cleaned_text = None
        else:
            # Normalize
            cleaned_text = normalize_text(cleaned_text)
            
            # Check utility
            is_useful, filter_reason = is_useful_content(cleaned_text)
            
            if not is_useful:
                logger.info(f"Filtering {raw_record['url']}: {filter_reason}")
                stats["filtered"] += 1
                cleaned_text = None
            else:
                filter_reason = None
                stats["kept"] += 1
        
        record = {
            "url": raw_record["url"],
            "title": raw_record.get("title", ""),
            "cleaned_text": cleaned_text,
            "text_length": len(cleaned_text.split()) if cleaned_text else 0,
            "language": "en",
            "cleaned_timestamp": datetime.utcnow().isoformat() + "Z",
            "filter_reason": filter_reason,
        }
        
        all_records.append(record)
    
    # Second pass: deduplicate
    logger.info("Deduplicating...")
    unique_records = deduplicat_by_hash(all_records)
    stats["duplicates"] = len(all_records) - len(unique_records)
    
    # Third pass: write to output
    with open(output_jsonl_file, 'w', encoding='utf-8') as f:
        for record in unique_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    # Compute statistics
    text_lengths = [r.get('text_length', 0) for r in unique_records if r.get('cleaned_text')]
    stats["avg_text_length"] = sum(text_lengths) / len(text_lengths) if text_lengths else 0
    
    # Log statistics
    logger.info(f"\n{'='*60}")
    logger.info(f"Cleaning Complete:")
    logger.info(f"  Total records: {stats['total']}")
    logger.info(f"  Kept: {stats['kept']}")
    logger.info(f"  Filtered: {stats['filtered']}")
    logger.info(f"  Duplicates removed: {stats['duplicates']}")
    logger.info(f"  Average text length: {stats['avg_text_length']:.0f} words")
    logger.info(f"  Output: {output_jsonl_file}")
    logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    batch_clean("data/raw/crawl_output.jsonl")
