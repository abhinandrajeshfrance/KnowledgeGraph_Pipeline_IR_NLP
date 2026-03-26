# MODULE 1: Web Crawling, Cleaning & NER — Detailed Plan

## Domain: European AI Research Ecosystem
**Seed URLs (10 sources):**
1. Inria (inria.fr/en)
2. DFKI (dfki.de/en)
3. ELLIS (ellis.eu)
4. MILA (mila.quebec/en)
5. PRAIRIE Institute (prairie-institute.fr)
6. NeurIPS (neurips.cc)
7. ICML (icml.cc)
8. ECAI (ecai2024.eu)
9. OpenAlex API (api.openalex.org)
10. Wikidata SPARQL (query.wikidata.org)

---

## PART 1: WEB CRAWLER DESIGN

### 1.1 Architecture & Components

**File:** `src/crawl/crawler.py`

**Core Functions:**
1. `fetch_robots_txt(domain: str) -> RobotFileParser`
   - Download and parse `robots.txt` from each domain
   - Check crawl-ability before fetching pages
   - Handle missing/malformed robots.txt gracefully

2. `is_crawlable(url: str, robot_parser) -> bool`
   - Respect `Disallow`, `Allow`, and `Crawl-Delay` directives
   - Default polite delay: 2–3 seconds between requests to same domain
   - Return False if crawling is disallowed

3. `fetch_page(url: str, timeout=10) -> str | None`
   - Use `httpx` or `requests` library
   - Set User-Agent: `Mozilla/5.0 (compatible; EUAIResearchCrawler/1.0 +https://yourgithub)`
   - Implement retry logic: max 2 retries with exponential backoff
   - Handle HTTP errors gracefully (4xx, 5xx, timeouts)
   - Return raw HTML or None if failed

4. `extract_text_trafilatura(html: str) -> str | None`
   - Use `trafilatura` library (already designed for "main content" extraction)
   - Remove boilerplate (nav, footer, ads, sidebars)
   - Normalize whitespace, remove extra newlines
   - Return cleaned text or None if extraction fails

5. `batch_crawl(seed_urls: List[str], output_file: str) -> None`
   - For each seed URL:
     * Fetch robots.txt and build parser
     * Fetch page content
     * Extract main text via trafilatura
     * Save to `output_file` (JSONL format)
   - Log crawl statistics: URLs attempted, successful, failed, average time/page

### 1.2 Politeness & Ethics

**Implemented Safeguards:**
- ✓ robots.txt compliance (mandatory before any request)
- ✓ Request delay per domain (2–3 sec default)
- ✓ Descriptive User-Agent header with project name
- ✓ Timeout per request (10 sec, no infinite hangs)
- ✓ Retry with backoff (avoid hammering on transient failures)
- ✓ Logging of all requests (for audit trail and reflection in report)

**Ethics Notes for Report:**
- Explain why crawling these sites is appropriate (public research institutions)
- Document respect for robots.txt and rate-limiting
- Mention that crawled data will not be redistributed commercially

### 1.3 Output Format

**File:** `data/raw/crawl_output.jsonl`

Each line is a JSON object:
```json
{
  "url": "https://inria.fr/en/research-centers/inria-paris",
  "fetch_timestamp": "2026-03-25T14:32:45Z",
  "http_status": 200,
  "raw_html_length": 45632,
  "content_type": "text/html",
  "title": "Inria Paris Centre",
  "fetch_time_sec": 1.2,
  "error": null
}
```

---

## PART 2: CLEANING PIPELINE

### 2.1 Architecture & Components

**File:** `src/crawl/cleaning.py`

**Core Functions:**
1. `load_raw_crawl(jsonl_file: str) -> Iterator[dict]`
   - Read raw crawl output
   - Validate JSON structure
   - Yield one record at a time for memory efficiency

2. `extract_main_text(html: str) -> str | None`
   - Re-apply trafilatura (or fallback to regex-based extraction if trafilatura fails)
   - Return main content text

3. `normalize_text(text: str) -> str`
   - Remove excess whitespace (collapse multiple spaces/newlines)
   - Convert to lowercase for later processing
   - Remove URLs, email addresses, phone numbers (optional cleaning for noise reduction)
   - Remove special Unicode characters (keep only printable ASCII + common diacritics)

4. `is_useful_content(text: str, min_words=500) -> bool`
   - Check text length (minimum 500 words to filter spurious/empty pages)
   - Check against stopword ratio (if >90% English stopwords, likely boilerplate)
   - Return True if content is useful

5. `deduplicat_by_hash(records: List[dict]) -> List[dict]`
   - Compute SHA-256 hash of normalized text
   - Remove exact duplicates (same content from multiple URLs)
   - Return unique records

6. `batch_clean(raw_jsonl_file: str, output_jsonl_file: str) -> None`
   - Load raw crawl output
   - For each record:
     * Extract main text
     * Normalize whitespace, case, special chars
     * Check if content is useful
     * Deduplicate
   - Log statistics: total URLs, kept after filtering, duplicates removed, average text length

### 2.2 Output Format

**File:** `data/cleaned/cleaned_output.jsonl`

Each line is a JSON object:
```json
{
  "url": "https://inria.fr/en/research-centers/inria-paris",
  "title": "Inria Paris Centre",
  "cleaned_text": "Inria Paris is a research centre located in Paris specializing in computer science...",
  "text_length": 4256,
  "language": "en",
  "cleaned_timestamp": "2026-03-25T14:35:10Z",
  "filter_reason": null
}
```

(Filtered-out URLs have `cleaned_text: null` and `filter_reason: "too_short"` or `"duplicate"`)

---

## PART 3: NAMED ENTITY RECOGNITION (NER)

### 3.1 Architecture & Components

**File:** `src/ie/ner.py`

**Core Functions:**
1. `load_spacy_model(model_name="en_core_web_trf") -> Language`
   - Load transformer-based spaCy model (or fallback to `en_core_web_sm`)
   - Ensure NLP pipeline includes: `tok2vec`, `morphologizer`, `parser`, `ner`, `attribute_ruler`, `lemmatizer`

2. `run_ner_on_text(text: str, nlp: Language) -> List[dict]`
   - Process text with spaCy NER
   - For each entity token:
     * Extract `text`, `label` (PERSON, ORG, GPE, DATE, MISC, PRODUCT, etc.)
     * Compute confidence (for transformer models, extract attention scores; for rule-based, use 1.0 or heuristic)
     * Capture sentence context (the sentence containing the entity)
   - Return list of entity dicts

3. `extract_entities_from_url(url: str, text: str, nlp: Language) -> List[dict]`
   - Run NER on text
   - For each entity, build a record including:
     * entity text
     * entity type (PERSON, ORG, GPE, DATE, MISC)
     * source URL
     * sentence context
     * confidence score
   - Filter out common false positives (e.g., standalone dates like "2025")

4. `batch_ner(cleaned_jsonl_file: str, output_jsonl_file: str) -> None`
   - Load cleaned text from `data/cleaned/cleaned_output.jsonl`
   - For each URL record:
     * Extract entities via spaCy NER
     * Store with source URL and confidence
   - Log statistics: total entities extracted, per-label breakdown, confidence distribution

### 3.2 Confidence Scoring Strategy

**For Transformer-based Models (en_core_web_trf):**
- Use attention weights from the transformer layer for the entity span
- Confidence = average attention score for the entity tokens
- Range: 0.0 to 1.0

**Fallback (if transformer unavailable):**
- Use `en_core_web_sm` + custom confidence heuristic:
  * PERSON: +0.9 if capitalized and recognized by NER
  * ORG: +0.85 if capitalized and recognized by NER + found in mentions (e.g., "INRIA", "DFKI")
  * GPE: +0.9 if in known location lists or recognized by NER
  * DATE: +0.95 if matches date patterns
  * MISC: +0.7 by default

### 3.3 Output Format

**File:** `data/entities.jsonl`

Each line is a JSON object:
```json
{
  "entity_text": "Marie Curie",
  "entity_type": "PERSON",
  "source_url": "https://inria.fr/en/research-centers/inria-paris",
  "sentence_context": "Marie Curie was a pioneering researcher in radioactivity.",
  "confidence": 0.92,
  "occurrence_index": 0,
  "extraction_timestamp": "2026-03-25T14:40:30Z"
}
```

**Additional CSV Export for Convenience:**

**File:** `data/entities.csv`

```csv
entity_text,entity_type,source_url,confidence,sentence_context
Marie Curie,PERSON,https://inria.fr/en/research-centers/inria-paris,0.92,"Marie Curie was a pioneering researcher in radioactivity."
DFKI,ORG,https://dfki.de/en,0.95,"DFKI is a leading AI research institute."
Paris,GPE,https://inria.fr/en,0.90,"Inria Paris is located in Paris."
```

---

## PART 4: AMBIGUITY CASES TRACKING

**File:** `src/ie/ambiguity_tracker.py`

### 4.1 Types of Ambiguities to Document

1. **Entity Name Collision (Same Name, Different Referents)**
   - Example: "Paris" (city in France vs. Paris Hilton person)
   - Tracked in: entity text + sentence context + source URL

2. **Acronym Ambiguity**
   - Example: "AI" (Artificial Intelligence vs. Appraisal Institute)
   - Solution: check context and limit to AI research domain

3. **Nested Entity Ambiguity**
   - Example: "Stanford University" tagged as both ORG and nested "Stanford" as GPE
   - Tracked: overlapping entity spans

### 4.2 Collection Strategy

**During NER:**
- Flag entities with confidence < 0.75 as "uncertain"
- Flag entities where multiple entity types match the same span (e.g., both PERSON and ORG for "Google")
- Log collisions where the same entity text appears in multiple sources with conflicting types or contexts

**Post-Processing:**
- Generate report: `data/ambiguity_examples.json`
- Document top 3-5 ambiguity cases with:
  * Entity text
  * Conflicting contexts/types
  * URLs where they appeared
  * Proposed disambiguation (manual review)

### 4.3 Output Format

**File:** `data/ambiguity_examples.json`

```json
{
  "ambiguities": [
    {
      "entity_text": "Paris",
      "ambiguity_type": "entity_name_collision",
      "occurrences": [
        {
          "url": "https://inria.fr/en",
          "context": "Inria Paris is located in Paris, France",
          "inferred_referent": "Paris, France (GPE)"
        },
        {
          "url": "https://neurips.cc/Conferences/2025/Schedule?type=Poster",
          "context": "Paris Hilton attended the conference",
          "inferred_referent": "Paris Hilton (PERSON)"
        }
      ],
      "notes": "Name collision: city vs. person. Resolved via context."
    },
    {
      "entity_text": "AI",
      "ambiguity_type": "acronym_ambiguity",
      "all_contexts": [
        {
          "url": "https://ellis.eu",
          "context": "ELLIS is a network for AI research"
        }
      ],
      "notes": "Acronym 'AI' appears in many contexts; domain constraint (AI research) helps resolve."
    }
  ]
}
```

---

## PART 5: FILE ORGANIZATION & DEPENDENCIES

### 5.1 Project Structure (Module 1)

```
project-root/
├─ src/
│  ├─ crawl/
│  │  ├─ __init__.py
│  │  ├─ crawler.py          # fetch_robots_txt, fetch_page, extract_text_trafilatura, batch_crawl
│  │  └─ cleaning.py         # normalize_text, is_useful_content, deduplicat_by_hash, batch_clean
│  ├─ ie/
│  │  ├─ __init__.py
│  │  ├─ ner.py              # run_ner_on_text, batch_ner
│  │  └─ ambiguity_tracker.py # flag_ambiguities, generate_ambiguity_report
│  └─ __init__.py
├─ data/
│  ├─ raw/
│  │  └─ crawl_output.jsonl      # raw fetch results
│  ├─ cleaned/
│  │  └─ cleaned_output.jsonl    # cleaned text
│  ├─ entities.jsonl             # extracted entities with confidence
│  ├─ entities.csv               # CSV export for convenience
│  ├─ ambiguity_examples.json    # documented ambiguities
│  └─ README.md                  # data dictionary
├─ notebooks/
│  └─ 01_crawl_ner_exploration.ipynb  # optional: exploratory analysis
├─ README.md
├─ requirements.txt              # httpx, trafilatura, spacy, rdflib, pandas, etc.
└─ .gitignore
```

### 5.2 Python Dependencies

**File:** `requirements.txt` (excerpt for Module 1)

```
httpx>=0.25.0
trafilatura>=1.8.0
spacy>=3.7.0
pandas>=2.0.0
requests>=2.31.0
urllib3>=2.0.0
```

**spaCy Model Download:**
```bash
python -m spacy download en_core_web_trf
# or fallback:
python -m spacy download en_core_web_sm
```

---

## PART 6: EXECUTION FLOW & MAIN ENTRY POINT

**File:** `src/crawl/run_module1.py`

```python
"""
Module 1 main orchestrator.
Runs: Crawl -> Clean -> NER -> Ambiguity Tracking
"""

if __name__ == "__main__":
    SEED_URLS = [
        "https://inria.fr/en",
        "https://dfki.de/en",
        "https://ellis.eu",
        "https://mila.quebec/en",
        "https://prairie-institute.fr",
        "https://neurips.cc",
        "https://icml.cc",
        "https://ecai2024.eu",
        # Note: OpenAlex and Wikidata are APIs, handled separately if needed
    ]
    
    # Step 1: Crawl
    print("[1/4] Crawling seed URLs...")
    batch_crawl(SEED_URLS, "data/raw/crawl_output.jsonl")
    
    # Step 2: Clean
    print("[2/4] Cleaning crawled content...")
    batch_clean("data/raw/crawl_output.jsonl", "data/cleaned/cleaned_output.jsonl")
    
    # Step 3: NER
    print("[3/4] Running Named Entity Recognition...")
    batch_ner("data/cleaned/cleaned_output.jsonl", "data/entities.jsonl")
    
    # Step 4: Ambiguity Tracking
    print("[4/4] Analyzing entity ambiguities...")
    generate_ambiguity_report("data/entities.jsonl", "data/ambiguity_examples.json")
    
    print("\n✓ Module 1 complete!")
    print(f"  Raw crawl:    data/raw/crawl_output.jsonl")
    print(f"  Cleaned text: data/cleaned/cleaned_output.jsonl")
    print(f"  Entities:     data/entities.jsonl")
    print(f"  Ambiguities:  data/ambiguity_examples.json")
```

---

## PART 7: MAPPING TO GRADING & LAB REQUIREMENTS

### Lab Session 1 Deliverables (from course document)

| Requirement | Delivered By | File |
|---|---|---|
| Build polite crawler (robots.txt, delay, User-Agent) | `src/crawl/crawler.py` | `data/raw/crawl_output.jsonl` |
| Clean HTML, remove boilerplate | `src/crawl/cleaning.py` | `data/cleaned/cleaned_output.jsonl` |
| Named Entity Recognition (5 types: PERSON, ORG, GPE, DATE, MISC) | `src/ie/ner.py` | `data/entities.jsonl` |
| Save entities with source URL + confidence | `src/ie/ner.py` | `data/entities.jsonl` + CSV |
| Document 3 ambiguity cases | `src/ie/ambiguity_tracker.py` | `data/ambiguity_examples.json` + Report section |
| Lab Report: methodology, ambiguity, scaling | Manual write-up | `reports/final_report.md` section 1 |

### Grading Breakdown (3 pts total)

| Criterion | Points | Implementation |
|---|---|---|
| Crawler quality + ethics | 1.0 | robots.txt check, delays, User-Agent, rate-limiting documented |
| Cleaning + NER | 1.0 | trafilatura-based cleaning, spaCy-based NER with 5+ entity types, confidence scoring |
| Ambiguity & reflection | 1.0 | 3+ documented ambiguity cases + scaling reflection in final report |

---

## PART 8: EXECUTION TIMELINE & CHECKLIST

### Development Checklist

- [ ] Create module structure (`src/crawl/`, `src/ie/`)
- [ ] Implement `src/crawl/crawler.py`: fetch_robots_txt, fetch_page, batch_crawl
- [ ] Implement `src/crawl/cleaning.py`: normalize_text, is_useful_content, batch_clean
- [ ] Implement `src/ie/ner.py`: load spaCy model, run_ner_on_text, batch_ner
- [ ] Implement `src/ie/ambiguity_tracker.py`: flag_ambiguities, generate report
- [ ] Test crawl on 2-3 seed URLs, verify robots.txt respect
- [ ] Verify cleaned text quality (spot-check 5 samples)
- [ ] Verify NER output (check entity types, confidence distribution)
- [ ] Generate ambiguity report and select top 3 cases
- [ ] Create `data/README.md` documenting all output files
- [ ] Write Module 1 section of final report

### Expected Statistics (Rough Estimates)

| Metric | Expected Range |
|---|---|
| Pages crawled | 8–20 pages (from 8–10 seed domains) |
| Successful crawls | 70–90% (some pages may be blocked or malformed) |
| Total entities extracted | 500–2000 (depending on page volume and entity density) |
| Average confidence score | 0.80–0.95 (transformer-based models are typically high confidence) |
| Ambiguous entities | 10–30 (top 3-5 to be documented) |

---

## PART 9: NOTES ON SEED SOURCES

### HTML-crawlable sources (direct crawling)
1. Inria, DFKI, ELLIS, MILA, PRAIRIE — institution homepages ✓
2. NeurIPS, ICML, ECAI — conference sites ✓

### API sources (special handling)
9. **OpenAlex API** (api.openalex.org)  
   - Not HTML crawlable; requires API calls
   - Module 1 focus is on web crawling, but can enrich entities in later modules
   - For now: skip in Module 1, use in Module 2 (entity linking phase)

10. **Wikidata SPARQL** (query.wikidata.org)
    - Also handled as API, skip in crawling phase
    - Use in Module 2 for entity alignment

---

## QUESTIONS FOR CONFIRMATION

Before I proceed to code implementation, please confirm:

1. **Confidence Scoring:** Should we prioritize transformer-based attention weights (if available) or heuristic-based scoring (simpler but less precise)?

2. **Minimum Content Length:** Is 500 words a good threshold, or should it be lower (e.g., 300) to capture shorter research pages?

3. **Entity Types:** Should we stick to PERSON, ORG, GPE, DATE, MISC (standard 5), or add PRODUCT/WORK_OF_ART for AI models/publications?

4. **Output Formats:** OK to output both JSONL (for processing) and CSV (for human review), or prefer JSONL only?

5. **Rate Limiting:** Is 2–3 seconds delay between requests acceptable, or should it be more conservative (5 sec)?

6. **Fallback Models:** If `en_core_web_trf` is unavailable, should we fall back to `en_core_web_sm` (smaller, less accurate) or raise an error?

Please confirm the plan above and answer any of the 6 questions that differ from your preferences, then I'll proceed to code implementation.
