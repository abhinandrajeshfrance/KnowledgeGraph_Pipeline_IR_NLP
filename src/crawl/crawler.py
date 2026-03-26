"""
Web Crawler for Knowledge Graph Construction
- Respects robots.txt
- Polite delays between requests
- Extracts main content using trafilatura
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CRAWL_DELAY = 2.5  # seconds between requests per domain
REQUEST_TIMEOUT = 10.0  # seconds
USER_AGENT = "Mozilla/5.0 (compatible; EUAIResearchCrawler/1.0 +https://github.com/your-repo)"


def fetch_robots_txt(domain: str) -> Optional[RobotFileParser]:
    """
    Fetch and parse robots.txt for a domain.
    
    Args:
        domain: Domain URL (e.g., 'https://inria.fr')
    
    Returns:
        RobotFileParser object or None if fetch fails
    """
    try:
        parsed = urlparse(domain)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        
        logger.info(f"✓ Fetched robots.txt for {parsed.netloc}")
        return rp
    except Exception as e:
        logger.warning(f"✗ Failed to fetch robots.txt for {domain}: {e}")
        return None


def is_crawlable(url: str, robot_parser: Optional[RobotFileParser], user_agent: str = "*") -> bool:
    """
    Check if a URL is allowed by robots.txt.
    
    Args:
        url: URL to check
        robot_parser: RobotFileParser object (or None to skip check)
        user_agent: User-Agent string for robots.txt check
    
    Returns:
        True if crawlable, False otherwise
    """
    if robot_parser is None:
        return True  # If we couldn't fetch robots.txt, assume crawlable
    
    return robot_parser.can_fetch(user_agent, url)


def fetch_page(url: str, timeout: float = REQUEST_TIMEOUT, retries: int = 2) -> Optional[str]:
    """
    Fetch a page with exponential backoff retry logic.
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        retries: Number of retry attempts
    
    Returns:
        HTML content as string, or None if all retries fail
    """
    headers = {"User-Agent": USER_AGENT}
    
    for attempt in range(retries + 1):
        try:
            with httpx.Client() as client:
                response = client.get(url, timeout=timeout, headers=headers, follow_redirects=True)
                response.raise_for_status()
                logger.info(f"✓ Fetched {url} (status: {response.status_code})")
                return response.text
        except httpx.HTTPStatusError as e:
            logger.warning(f"✗ HTTP {e.response.status_code} for {url}")
            return None
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            wait = 2 ** attempt
            if attempt < retries:
                logger.warning(f"✗ Timeout/Connection error for {url}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"✗ Failed to fetch {url} after {retries + 1} attempts")
                return None
        except Exception as e:
            logger.error(f"✗ Unexpected error fetching {url}: {e}")
            return None


def extract_text_trafilatura(html: str) -> Optional[str]:
    """
    Extract main content from HTML using trafilatura.
    
    Args:
        html: HTML content as string
    
    Returns:
        Cleaned text, or None if extraction fails
    """
    try:
        text = trafilatura.extract(html, include_comments=False, favor_precision=True)
        return text
    except Exception as e:
        logger.warning(f"✗ Trafilatura extraction failed: {e}")
        return None


def batch_crawl(seed_urls: list, output_file: str = "data/raw/crawl_output.jsonl") -> None:
    """
    Crawl a batch of seed URLs and save results to JSONL.
    
    Args:
        seed_urls: List of seed URLs
        output_file: Path to output JSONL file
    """
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    stats = {
        "total_urls": len(seed_urls),
        "successful": 0,
        "failed": 0,
        "times": [],
    }
    
    # Group URLs by domain for per-domain rate limiting
    domain_last_fetch = {}
    
    with open(output_file, "w", encoding="utf-8") as f:
        for url in seed_urls:
            parsed = urlparse(url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            
            # Rate limit: wait if we fetched from this domain recently
            if domain in domain_last_fetch:
                elapsed = time.time() - domain_last_fetch[domain]
                if elapsed < CRAWL_DELAY:
                    wait_time = CRAWL_DELAY - elapsed
                    logger.info(f"  Waiting {wait_time:.1f}s before next request to {parsed.netloc}...")
                    time.sleep(wait_time)
            
            # Fetch robots.txt and check crawlability
            robot_parser = fetch_robots_txt(domain)
            if not is_crawlable(url, robot_parser, USER_AGENT):
                logger.warning(f"✗ Crawling disallowed by robots.txt for {url}")
                stats["failed"] += 1
                continue
            
            # Fetch page
            start_time = time.time()
            html = fetch_page(url)
            fetch_time = time.time() - start_time
            stats["times"].append(fetch_time)
            
            if html is None:
                stats["failed"] += 1
                record = {
                    "url": url,
                    "fetch_timestamp": datetime.utcnow().isoformat() + "Z",
                    "http_status": None,
                    "raw_html_length": 0,
                    "content_type": None,
                    "title": None,
                    "fetch_time_sec": fetch_time,
                    "raw_html": None,
                    "error": "fetch_failed",
                }
            else:
                stats["successful"] += 1
                title = extract_title_from_html(html) or ""
                record = {
                    "url": url,
                    "fetch_timestamp": datetime.utcnow().isoformat() + "Z",
                    "http_status": 200,
                    "raw_html_length": len(html),
                    "content_type": "text/html",
                    "title": title,
                    "fetch_time_sec": fetch_time,
                    "raw_html": html,
                    "error": None,
                }
            
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            domain_last_fetch[domain] = time.time()
    
    # Log statistics
    avg_time = sum(stats["times"]) / len(stats["times"]) if stats["times"] else 0
    logger.info(f"\n{'='*60}")
    logger.info(f"Crawl Complete:")
    logger.info(f"  Total URLs: {stats['total_urls']}")
    logger.info(f"  Successful: {stats['successful']}")
    logger.info(f"  Failed: {stats['failed']}")
    logger.info(f"  Average fetch time: {avg_time:.2f}s")
    logger.info(f"  Output: {output_file}")
    logger.info(f"{'='*60}\n")


def extract_title_from_html(html: str) -> Optional[str]:
    """Extract title from HTML <title> tag."""
    import re
    match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    return match.group(1).strip() if match else None


if __name__ == "__main__":
    # Example usage
    SEED_URLS = [
        "https://inria.fr/en",
        "https://ellis.eu",
    ]
    batch_crawl(SEED_URLS)
