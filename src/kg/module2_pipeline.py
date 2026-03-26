"""
Module 2 pipeline:
1) Build ontology schema (already created in kg_artifacts/schema.ttl)
2) Build base RDF graph from filtered entities
3) Link entities to Wikidata via public SPARQL endpoint
4) Apply predicate alignment metadata
5) Expand graph with SPARQL query packs Q1/Q2/Q3
6) Compute KB statistics before/after expansion
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import httpx
from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef
from rdflib.namespace import PROV, SKOS, XSD

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
KG_DIR = ROOT / "kg_artifacts"
LINK_DIR = KG_DIR / "linking"

ENTITY_INPUT = DATA_DIR / "entities_final.jsonl"
SCHEMA_FILE = KG_DIR / "schema.ttl"
BASE_GRAPH_FILE = KG_DIR / "base_graph.ttl"
ALIGNED_GRAPH_FILE = KG_DIR / "aligned_graph.ttl"
EXPANDED_GRAPH_FILE = KG_DIR / "expanded_graph.ttl"
LINK_SUMMARY_FILE = LINK_DIR / "linking_summary.json"
AUTO_LINKS_FILE = LINK_DIR / "auto_links.jsonl"
CANDIDATE_LINKS_FILE = LINK_DIR / "candidate_links.jsonl"
REJECTED_LINKS_FILE = LINK_DIR / "rejected_links.jsonl"
EXPANSION_LOG_FILE = KG_DIR / "expansion_log.jsonl"
STATS_FILE = KG_DIR / "kb_stats.json"

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
REQUEST_HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "IRNLP-KG-Module2/1.0 (educational project; polite endpoint usage)",
}

_SPARQL_CLIENT: Optional[httpx.Client] = None

EX = Namespace("http://example.org/ai-kg/")
WD = Namespace("http://www.wikidata.org/entity/")
WDT = Namespace("http://www.wikidata.org/prop/direct/")

AUTO_THRESHOLD = 0.85
CANDIDATE_THRESHOLD = 0.60
POLITE_DELAY_SECONDS = 2.5
MAX_RETRIES = 3

TYPE_TO_CLASS = {
    "PERSON": EX.Person,
    "ORG": EX.Organization,
    "GPE": EX.Location,
    "LOC": EX.Location,
    "FAC": EX.Location,
    "NORP": EX.ResearchTopic,
    "LANGUAGE": EX.ResearchTopic,
    "WORK_OF_ART": EX.Event,
    "PRODUCT": EX.Program,
    "LAW": EX.Program,
    "DATE": EX.Event,
    "CARDINAL": EX.Entity,
    "ORDINAL": EX.Entity,
    "PERCENT": EX.Entity,
}

CLASS_HINTS = {
    "PERSON": ["Q5"],  # Human - strict requirement
    "ORG": ["Q43229", "Q2385804", "Q31855", "Q783794"],  # Organization, enterprise, institution, research institute
    "GPE": ["Q6256", "Q515", "Q82794"],  # Country, city, geographical region
    "LOC": ["Q82794", "Q2221906", "Q6256"],  # Geographical region, natural feature, country
    "FAC": ["Q13226383", "Q41176"],  # Building, structure
}

PREDICATE_ALIGNMENT = {
    "affiliatedWith": {"wikidata": "P108", "confidence": 0.92, "note": "Employer / affiliation"},
    "participatesIn": {"wikidata": "P1344", "confidence": 0.88, "note": "Participant in"},
    "locatedIn": {"wikidata": "P131", "confidence": 0.87, "note": "Located in administrative entity"},
    "focusesOn": {"wikidata": "P101", "confidence": 0.84, "note": "Field of work"},
    "collaboratesWith": {"wikidata": "P463", "confidence": 0.75, "note": "Member of / collaboration proxy"},
}

PERSON_STRIP_TOKENS = {
    "ai",
    "lab",
    "labs",
    "group",
    "team",
    "research",
    "center",
    "centre",
    "institute",
}

TRAILING_NOISE_TOKENS = {
    "ai",
    "lab",
    "labs",
    "group",
    "team",
    "program",
    "programme",
    "key",
    "news",
    "conference",
}

ORG_QUERY_SUFFIXES = ["organization", "institute", "research"]

PERSON_JOINERS = {"de", "del", "da", "di", "van", "von", "bin", "al", "la", "le"}
TARGET_LINK_TYPES = {"PERSON", "ORG", "GPE", "LOC", "FAC"}


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned[:60] if cleaned else "entity"


def _entity_uri(entity_text: str, entity_type: str, source_url: str, char_start: Optional[int]) -> URIRef:
    key = f"{entity_text}|{entity_type}|{source_url}|{char_start}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return EX[f"entity/{_slug(entity_text)}-{digest}"]


def _load_entities(path: Path) -> List[Dict[str, Any]]:
    entities: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entities.append(json.loads(line))
    return entities


def _bind_prefixes(graph: Graph) -> None:
    graph.bind("ex", EX)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)
    graph.bind("owl", OWL)
    graph.bind("xsd", XSD)
    graph.bind("skos", SKOS)
    graph.bind("prov", PROV)
    graph.bind("wd", WD)
    graph.bind("wdt", WDT)


def step2_build_base_graph() -> Dict[str, Any]:
    KG_DIR.mkdir(parents=True, exist_ok=True)
    entities = _load_entities(ENTITY_INPUT)

    graph = Graph()
    _bind_prefixes(graph)

    seen_entities: Set[URIRef] = set()
    for ent in entities:
        text = ent.get("entity_text", "").strip()
        etype = ent.get("entity_type", "")
        source_url = ent.get("source_url", "")
        char_start = ent.get("char_start")
        confidence = float(ent.get("confidence", 0.0))

        entity_uri = _entity_uri(text, etype, source_url, char_start)
        seen_entities.add(entity_uri)

        cls = TYPE_TO_CLASS.get(etype, EX.Entity)
        graph.add((entity_uri, RDF.type, cls))
        graph.add((entity_uri, RDF.type, EX.Entity))
        graph.add((entity_uri, RDFS.label, Literal(text)))
        graph.add((entity_uri, EX.entityType, Literal(etype)))
        graph.add((entity_uri, EX.confidenceScore, Literal(confidence, datatype=XSD.decimal)))

        if source_url:
            graph.add((entity_uri, EX.sourceUrl, Literal(source_url, datatype=XSD.anyURI)))
            graph.add((entity_uri, PROV.wasDerivedFrom, URIRef(source_url)))

        ts = ent.get("extraction_timestamp")
        if ts:
            graph.add((entity_uri, EX.extractionTimestamp, Literal(ts, datatype=XSD.dateTime)))

        sent = ent.get("sentence_context")
        if sent:
            graph.add((entity_uri, SKOS.altLabel, Literal(sent[:300])))

    graph.serialize(destination=str(BASE_GRAPH_FILE), format="turtle")

    return {
        "input_entities": len(entities),
        "unique_entity_nodes": len(seen_entities),
        "triple_count": len(graph),
        "output": str(BASE_GRAPH_FILE),
    }


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.NetworkError):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return exc.response.status_code == 429
    msg = str(exc).lower()
    if "getaddrinfo failed" in msg or "winerror 10060" in msg:
        return True
    return False


def _sparql_select(query: str, timeout: int = 30) -> List[Dict[str, str]]:
    params = {"format": "json", "query": query}

    last_exc: Optional[Exception] = None
    timeout_cfg = httpx.Timeout(timeout=timeout, connect=min(5.0, float(timeout)), read=float(timeout))
    for attempt in range(MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout_cfg, follow_redirects=True, http2=False) as client:
                resp = client.get(WIKIDATA_SPARQL, params=params, headers=REQUEST_HEADERS)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if not _is_retryable_error(exc) or attempt >= MAX_RETRIES:
                raise
            # Exponential backoff: 2.5s, 5s, 10s, 20s
            backoff = 2.5 * (2 ** attempt)
            print(f"[Retry] Attempt {attempt+1}/{MAX_RETRIES+1}: Waiting {backoff}s before retry. Error: {exc}")
            time.sleep(backoff)
    else:
        if last_exc is not None:
            raise last_exc
        return []

    results = []
    for row in data.get("results", {}).get("bindings", []):
        parsed = {k: v.get("value", "") for k, v in row.items()}
        results.append(parsed)
    return results


def _class_filter_values(entity_type: str) -> str:
    hints = CLASS_HINTS.get(entity_type, [])
    return ", ".join(f"wd:{qid}" for qid in hints)


def _sparql_escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _normalize_for_query(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    ascii_text = ascii_text.replace("’", " ").replace("'", " ")
    ascii_text = re.sub(r"[^A-Za-z0-9\s-]", " ", ascii_text)
    ascii_text = re.sub(r"\s+", " ", ascii_text).strip()
    return ascii_text


def _strip_trailing_noise_tokens(text: str) -> str:
    parts = [p for p in text.split() if p]
    while parts and parts[-1].lower() in TRAILING_NOISE_TOKENS:
        parts.pop()
    return " ".join(parts)


def _normalize_person_name(text: str) -> str:
    text = _normalize_for_query(text)
    text = _strip_trailing_noise_tokens(text)
    words = [w for w in text.split() if w]
    filtered: List[str] = []
    for w in words:
        wl = w.lower()
        if wl in PERSON_STRIP_TOKENS:
            continue
        if w[0].isupper() or wl in PERSON_JOINERS:
            filtered.append(w)

    # Prefer full-name queries (first name + last name) for PERSON entities.
    if len(filtered) >= 2:
        return " ".join(filtered[:2])  # Use first two capitalized words
    if len(words) >= 2:
        # Fall back to first two tokens even if not all capitalized
        return " ".join(words[:2])
    return ""


def _extract_person_names_from_context(context: str) -> List[str]:
    if not context:
        return []
    norm = _normalize_for_query(context)
    # Find likely full-name spans like "Peter Eisenman" or "Shuyu Dong".
    spans = re.findall(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,2}\b", norm)
    cleaned = []
    for span in spans:
        if len(span.split()) >= 2:
            cleaned.append(span)
    return list(dict.fromkeys(cleaned))


def _levenshtein_ratio(a: str, b: str) -> float:
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
    set_a = set(re.findall(r"[a-z0-9]+", a.lower()))
    set_b = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _score_candidate(
    candidate_label: str,
    matched_text: str,
    matched_via: str,
    query_name: str,
    entity_type: str,
    types: Iterable[str],
) -> float:
    norm_query = _normalize_for_query(query_name).lower()
    norm_label = _normalize_for_query(candidate_label).lower()
    norm_matched = _normalize_for_query(matched_text).lower()

    # String similarity: combine Levenshtein and token overlap
    lev_score = max(_levenshtein_ratio(norm_query, norm_label), _levenshtein_ratio(norm_query, norm_matched))
    tok_score = max(_token_overlap(norm_query, norm_label), _token_overlap(norm_query, norm_matched))
    string_similarity = 0.55 * lev_score + 0.45 * tok_score  # Weighted combination

    # Label match score: how well does query match the returned label/text?
    if norm_query == norm_matched or norm_query == norm_label:
        label_match_score = 1.0
    elif norm_query in norm_matched or norm_matched in norm_query:
        label_match_score = 0.85
    elif tok_score >= 0.6:
        label_match_score = 0.75
    elif tok_score >= 0.4:
        label_match_score = 0.55
    else:
        label_match_score = 0.40

    # Boost if matched via rdfs:label (more reliable than altLabel)
    if matched_via == "rdfs:label":
        label_match_score = min(1.0, label_match_score + 0.10)

    # Type match score: does the Wikidata result have the expected type?
    hint_set = set(CLASS_HINTS.get(entity_type, []))
    type_match_score = 1.0 if any(t.split("/")[-1] in hint_set for t in types) else 0.4

    # Final score: weighted combination of three factors
    # String similarity is primary, label matching supports it, type is a modifier
    final_score = (0.45 * string_similarity) + (0.30 * label_match_score) + (0.25 * type_match_score)
    return round(final_score, 4)


def _entity_name_candidates(entity_text: str, entity_type: str, context: str = "") -> List[str]:
    norm = _normalize_for_query(entity_text)
    norm = _strip_trailing_noise_tokens(norm)

    candidates: List[str] = []
    if entity_type == "PERSON":
        person_name = _normalize_person_name(entity_text)
        if person_name:
            candidates.append(person_name)
        # Use context to recover full person names where entity text is partial.
        context_names = _extract_person_names_from_context(context)
        for name in context_names[:3]:
            if person_name and person_name.split()[0].lower() not in name.lower():
                continue
            candidates.append(name)
    else:
        if norm:
            candidates.append(norm)

    if entity_text.isupper() and len(entity_text) <= 8:
        candidates.append(entity_text.title())

    if entity_type == "ORG":
        base = candidates[0] if candidates else norm
        # Generate org-specific queries with keywords
        if base:
            for kw in ORG_QUERY_SUFFIXES:
                candidates.append(f"{base} {kw}")
            # Also try just the base name first (before modified versions)
            candidates.insert(0, base)

    return list(dict.fromkeys(c.strip() for c in candidates if c.strip()))


def _type_constraint_clause(entity_type: str) -> str:
    if entity_type == "PERSON":
        return "?item wdt:P31/wdt:P279* wd:Q5 ."  # PERSON or subclass of human
    if entity_type == "ORG":
        return "?item wdt:P31/wdt:P279* wd:Q43229 ."  # Organization or subclass
    if entity_type in {"GPE", "LOC"}:
        return """
        VALUES ?locClass { wd:Q6256 wd:Q515 wd:Q82794 }
        ?item wdt:P31/wdt:P279* ?locClass .
        """
    return ""


def _query_link_candidates(entity_text: str, entity_type: str, context: str = "") -> List[Dict[str, Any]]:
    names = _entity_name_candidates(entity_text, entity_type, context=context)
    if not names:
        return []
    values = " ".join(f'"{_sparql_escape_literal(n)}"@en' for n in names)
    type_clause = _type_constraint_clause(entity_type)

    query = f"""
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

        SELECT DISTINCT ?item ?itemLabel ?matchedText ?matchedVia ?type ?name WHERE {{
            VALUES ?name {{ {values} }}

            {{
                ?item rdfs:label ?matchedText .
                FILTER(LANG(?matchedText) = "en")
                BIND("rdfs:label" AS ?matchedVia)
                FILTER(CONTAINS(LCASE(STR(?matchedText)), LCASE(STR(?name))) ||
                       CONTAINS(LCASE(STR(?name)), LCASE(STR(?matchedText))))
            }}
            UNION
            {{
                ?item skos:altLabel ?matchedText .
                FILTER(LANG(?matchedText) = "en")
                BIND("skos:altLabel" AS ?matchedVia)
                FILTER(CONTAINS(LCASE(STR(?matchedText)), LCASE(STR(?name))) ||
                       CONTAINS(LCASE(STR(?name)), LCASE(STR(?matchedText))))
            }}

            OPTIONAL {{
                ?item rdfs:label ?itemLabel .
                FILTER(LANG(?itemLabel) = "en")
            }}
            OPTIONAL {{ ?item wdt:P31 ?type . }}
            {type_clause}
        }}
        LIMIT 5
    """

    rows = _sparql_select(query, timeout=30)
    candidates: List[Dict[str, Any]] = []
    for row in rows:
        qid = row.get("item", "").split("/")[-1]
        if not qid:
            continue
        candidate: Dict[str, Any] = {
            "qid": qid,
            "label": row.get("itemLabel", "") or row.get("matchedText", ""),
            "types": [row["type"]] if row.get("type") else [],
            "matched_text": row.get("matchedText", ""),
            "matched_via": row.get("matchedVia", ""),
            "query_name": row.get("name", "") or names[0],
        }
        candidates.append(candidate)

    return candidates


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def step3_entity_linking() -> Dict[str, Any]:
    LINK_DIR.mkdir(parents=True, exist_ok=True)

    graph = Graph()
    graph.parse(str(BASE_GRAPH_FILE), format="turtle")
    _bind_prefixes(graph)

    # Use one representative local node per (label, type) to avoid redundant calls.
    representatives: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for s, _, o in graph.triples((None, RDFS.label, None)):
        label = str(o)
        etype_obj = graph.value(s, EX.entityType)
        if etype_obj is None:
            continue
        etype = str(etype_obj)
        context_obj = graph.value(s, SKOS.altLabel)
        key = (label, etype)
        representatives.setdefault(
            key,
            {
                "uri": s,
                "context": str(context_obj) if context_obj else "",
            },
        )

    auto_links: List[Dict[str, Any]] = []
    candidate_links: List[Dict[str, Any]] = []
    rejected_links: List[Dict[str, Any]] = []

    total = len(representatives)
    delay_seconds = POLITE_DELAY_SECONDS
    print(f"[Step3] Linking {total} unique entities...")

    for idx, ((label, etype), rep) in enumerate(representatives.items(), start=1):
        local_uri = rep["uri"]
        context = rep.get("context", "")
        queried_endpoint = False
        if idx == 1 or idx % 10 == 0 or idx == total:
            print(f"[Step3] Progress {idx}/{total} (auto: {len(auto_links)}, cand: {len(candidate_links)}, rej: {len(rejected_links)})")

        if etype not in TARGET_LINK_TYPES:
            rejected_links.append(
                {
                    "local_uri": str(local_uri),
                    "entity_text": label,
                    "entity_type": etype,
                    "status": "rejected",
                    "reason": "unsupported_type_for_linking",
                    "score": 0.0,
                }
            )
            continue

        candidates: List[Dict[str, Any]] = []
        try:
            queried_endpoint = True
            raw_candidates = _query_link_candidates(label, etype, context=context)
            best_by_qid: Dict[str, Dict[str, Any]] = {}
            for c in raw_candidates:
                score = _score_candidate(
                    c.get("label", ""),
                    c.get("matched_text", ""),
                    c.get("matched_via", ""),
                    c.get("query_name", label),
                    etype,
                    c.get("types", []),
                )
                qid = c.get("qid")
                if not qid:
                    continue
                existing = best_by_qid.get(qid)
                if existing is None or score > float(existing.get("score", 0.0)):
                    best_by_qid[qid] = {**c, "score": round(score, 4)}
                elif c.get("types"):
                    merged_types = set(existing.get("types", [])) | set(c.get("types", []))
                    existing["types"] = sorted(merged_types)

            candidates = list(best_by_qid.values())
            candidates.sort(key=lambda x: x["score"], reverse=True)
        except Exception as exc:  # noqa: BLE001
            if _is_retryable_error(exc):
                delay_seconds = min(2.0, delay_seconds + 0.25)
            rejected_links.append(
                {
                    "local_uri": str(local_uri),
                    "entity_text": label,
                    "entity_type": etype,
                    "status": "rejected",
                    "reason": f"query_error: {exc}",
                    "score": 0.0,
                }
            )
            time.sleep(delay_seconds)
            continue

        if not candidates:
            rejected_links.append(
                {
                    "local_uri": str(local_uri),
                    "entity_text": label,
                    "entity_type": etype,
                    "status": "rejected",
                    "reason": "no_candidate",
                    "score": 0.0,
                }
            )
        else:
            best = candidates[0]
            score = float(best["score"])
            row = {
                "local_uri": str(local_uri),
                "entity_text": label,
                "entity_type": etype,
                "wikidata_qid": best["qid"],
                "wikidata_uri": f"http://www.wikidata.org/entity/{best['qid']}",
                "wikidata_label": best["label"],
                "matched_text": best.get("matched_text", ""),
                "matched_via": best.get("matched_via", ""),
                "query_name": best.get("query_name", label),
                "score": score,
                "candidate_count": len(candidates),
            }
            if score >= AUTO_THRESHOLD:  # Changed from > to >=
                row["status"] = "auto_linked"
                auto_links.append(row)
                graph.add((local_uri, OWL.sameAs, WD[best["qid"]]))
            elif CANDIDATE_THRESHOLD <= score < AUTO_THRESHOLD:  # Changed logic
                row["status"] = "candidate"
                candidate_links.append(row)
            else:
                row["status"] = "rejected"
                row["reason"] = "below_threshold"
                rejected_links.append(row)

        # Polite usage constraint: adaptive delay based on endpoint responsiveness
        if queried_endpoint and idx < len(representatives):
            time.sleep(delay_seconds)

    _write_jsonl(AUTO_LINKS_FILE, auto_links)
    _write_jsonl(CANDIDATE_LINKS_FILE, candidate_links)
    _write_jsonl(REJECTED_LINKS_FILE, rejected_links)

    summary = {
        "total_unique_entities": len(representatives),
        "auto_linked": len(auto_links),
        "candidate": len(candidate_links),
        "rejected": len(rejected_links),
        "linked_percentage": round((len(auto_links) / len(representatives)) * 100, 2) if representatives else 0.0,
        "auto_threshold": AUTO_THRESHOLD,
        "candidate_range": [CANDIDATE_THRESHOLD, AUTO_THRESHOLD],
    }
    LINK_SUMMARY_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    graph.serialize(destination=str(ALIGNED_GRAPH_FILE), format="turtle")
    return summary


def step4_apply_predicate_alignment() -> Dict[str, Any]:
    graph = Graph()
    graph.parse(str(ALIGNED_GRAPH_FILE), format="turtle")
    _bind_prefixes(graph)

    alignment_rows = []
    for ex_prop, info in PREDICATE_ALIGNMENT.items():
        ex_uri = EX[ex_prop]
        wd_uri = WDT[info["wikidata"]]
        graph.add((ex_uri, OWL.equivalentProperty, wd_uri))
        graph.add((ex_uri, RDFS.comment, Literal(info["note"])))
        graph.add((ex_uri, EX.confidenceScore, Literal(info["confidence"], datatype=XSD.decimal)))
        alignment_rows.append(
            {
                "local_property": str(ex_uri),
                "wikidata_property": str(wd_uri),
                "confidence": info["confidence"],
                "note": info["note"],
            }
        )

    mapping_file = KG_DIR / "predicate_alignment.json"
    mapping_file.write_text(json.dumps(alignment_rows, indent=2), encoding="utf-8")

    graph.serialize(destination=str(ALIGNED_GRAPH_FILE), format="turtle")

    return {
        "aligned_properties": len(alignment_rows),
        "mapping_file": str(mapping_file),
        "output_graph": str(ALIGNED_GRAPH_FILE),
    }


def _run_q1(qid: str) -> List[Dict[str, str]]:
    query = f"""
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

    SELECT DISTINCT ?label ?altLabel WHERE {{
      BIND(wd:{qid} AS ?item)
      OPTIONAL {{ ?item rdfs:label ?label . FILTER(LANG(?label) = \"en\") }}
      OPTIONAL {{ ?item skos:altLabel ?altLabel . FILTER(LANG(?altLabel) = \"en\") }}
    }}
    LIMIT 25
    """
    return _sparql_select(query, timeout=20)


def _run_q2(qid: str) -> List[Dict[str, str]]:
    query = f"""
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?org ?orgLabel WHERE {{
      BIND(wd:{qid} AS ?item)
      ?item wdt:P108 ?org .
      ?org rdfs:label ?orgLabel .
      FILTER(LANG(?orgLabel) = \"en\")
    }}
    LIMIT 20
    """
    return _sparql_select(query, timeout=20)


def _run_q3(qid: str) -> List[Dict[str, str]]:
    query = f"""
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?country ?countryLabel ?admin ?adminLabel WHERE {{
      BIND(wd:{qid} AS ?item)
      OPTIONAL {{
        ?item wdt:P17 ?country .
        ?country rdfs:label ?countryLabel .
        FILTER(LANG(?countryLabel) = \"en\")
      }}
      OPTIONAL {{
        ?item wdt:P131 ?admin .
        ?admin rdfs:label ?adminLabel .
        FILTER(LANG(?adminLabel) = \"en\")
      }}
    }}
    LIMIT 20
    """
    return _sparql_select(query, timeout=20)


def step5_expand_q1_q2_q3() -> Dict[str, Any]:
    graph = Graph()
    graph.parse(str(ALIGNED_GRAPH_FILE), format="turtle")
    _bind_prefixes(graph)

    auto_links = []
    if AUTO_LINKS_FILE.exists():
        with AUTO_LINKS_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    auto_links.append(json.loads(line))

    expansion_log = []
    added = 0

    total = len(auto_links)
    delay_seconds = POLITE_DELAY_SECONDS
    print(f"[Step5] Expanding Q1/Q2/Q3 for {total} auto-linked entities...")

    for idx, link in enumerate(auto_links, start=1):
        if idx == 1 or idx % 10 == 0 or idx == total:
            print(f"[Step5] Progress {idx}/{total}")
        local_uri = URIRef(link["local_uri"])
        qid = link["wikidata_qid"]
        wd_uri = WD[qid]

        try:
            q1_rows: List[Dict[str, str]] = []
            q2_rows: List[Dict[str, str]] = []
            q3_rows: List[Dict[str, str]] = []

            try:
                q1_rows = _run_q1(qid)
            except Exception as exc:  # noqa: BLE001
                if _is_retryable_error(exc):
                    delay_seconds = min(2.0, delay_seconds + 0.25)
                expansion_log.append(
                    {
                        "local_uri": str(local_uri),
                        "qid": qid,
                        "status": "q1_error",
                        "error": str(exc),
                    }
                )

            for row in q1_rows:
                if row.get("label"):
                    graph.add((local_uri, RDFS.label, Literal(row["label"])))
                    added += 1
                if row.get("altLabel"):
                    graph.add((local_uri, SKOS.altLabel, Literal(row["altLabel"])))
                    added += 1

            try:
                q2_rows = _run_q2(qid)
            except Exception as exc:  # noqa: BLE001
                if _is_retryable_error(exc):
                    delay_seconds = min(2.0, delay_seconds + 0.25)
                expansion_log.append(
                    {
                        "local_uri": str(local_uri),
                        "qid": qid,
                        "status": "q2_error",
                        "error": str(exc),
                    }
                )

            for row in q2_rows:
                org_uri = URIRef(row["org"])
                graph.add((local_uri, EX.affiliatedWith, org_uri))
                if row.get("orgLabel"):
                    graph.add((org_uri, RDFS.label, Literal(row["orgLabel"])))
                added += 2

            try:
                q3_rows = _run_q3(qid)
            except Exception as exc:  # noqa: BLE001
                if _is_retryable_error(exc):
                    delay_seconds = min(2.0, delay_seconds + 0.25)
                expansion_log.append(
                    {
                        "local_uri": str(local_uri),
                        "qid": qid,
                        "status": "q3_error",
                        "error": str(exc),
                    }
                )

            for row in q3_rows:
                if row.get("country"):
                    country_uri = URIRef(row["country"])
                    graph.add((local_uri, EX.locatedIn, country_uri))
                    if row.get("countryLabel"):
                        graph.add((country_uri, RDFS.label, Literal(row["countryLabel"])))
                    added += 2
                if row.get("admin"):
                    admin_uri = URIRef(row["admin"])
                    graph.add((local_uri, EX.locatedIn, admin_uri))
                    if row.get("adminLabel"):
                        graph.add((admin_uri, RDFS.label, Literal(row["adminLabel"])))
                    added += 2

            expansion_log.append(
                {
                    "local_uri": str(local_uri),
                    "qid": qid,
                    "status": "expanded",
                    "q1_rows": len(q1_rows),
                    "q2_rows": len(q2_rows),
                    "q3_rows": len(q3_rows),
                }
            )
        except Exception as exc:  # noqa: BLE001
            expansion_log.append(
                {
                    "local_uri": str(local_uri),
                    "qid": qid,
                    "status": "error",
                    "error": str(exc),
                }
            )

        # Polite usage: one second between endpoint requests batches.
        if idx < len(auto_links):
            time.sleep(delay_seconds)

    _write_jsonl(EXPANSION_LOG_FILE, expansion_log)
    graph.serialize(destination=str(EXPANDED_GRAPH_FILE), format="turtle")

    return {
        "auto_linked_entities_expanded": len(auto_links),
        "expansion_log_entries": len(expansion_log),
        "added_triple_operations": added,
        "output": str(EXPANDED_GRAPH_FILE),
    }


def _relation_breakdown(graph: Graph) -> Dict[str, int]:
    counter = Counter()
    for _, p, _ in graph:
        counter[str(p)] += 1
    return dict(counter)


def _node_degree(graph: Graph) -> Tuple[float, Dict[str, int]]:
    adj: Dict[str, Set[str]] = defaultdict(set)
    for s, p, o in graph:
        if isinstance(s, URIRef):
            adj[str(s)]
        if isinstance(o, URIRef):
            adj[str(o)]
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            # Ignore rdf:type edges to class nodes for degree realism.
            if str(p) == str(RDF.type):
                continue
            adj[str(s)].add(str(o))
            adj[str(o)].add(str(s))

    if not adj:
        return 0.0, {}
    degrees = {node: len(neigh) for node, neigh in adj.items()}
    avg = sum(degrees.values()) / len(degrees)
    return round(avg, 4), degrees


def _count_linked_entities(graph: Graph) -> int:
    linked = set()
    for s, _, o in graph.triples((None, OWL.sameAs, None)):
        if str(o).startswith(str(WD)):
            linked.add(str(s))
    return len(linked)


def _count_entity_nodes(graph: Graph) -> int:
    return len({str(s) for s, _, _ in graph.triples((None, RDF.type, EX.Entity))})


def _compute_stats(graph_path: Path) -> Dict[str, Any]:
    graph = Graph()
    graph.parse(str(graph_path), format="turtle")

    triple_count = len(graph)
    entity_count = _count_entity_nodes(graph)
    linked_count = _count_linked_entities(graph)
    linked_pct = round((linked_count / entity_count) * 100, 2) if entity_count else 0.0
    relation_counts = _relation_breakdown(graph)
    avg_degree, _ = _node_degree(graph)

    return {
        "graph_file": str(graph_path),
        "triple_count": triple_count,
        "entity_count": entity_count,
        "linked_entity_count": linked_count,
        "linked_entity_percent": linked_pct,
        "relation_type_breakdown": relation_counts,
        "average_node_degree": avg_degree,
    }


def step6_compute_stats() -> Dict[str, Any]:
    before = _compute_stats(ALIGNED_GRAPH_FILE)
    after = _compute_stats(EXPANDED_GRAPH_FILE)

    stats = {"before_expansion": before, "after_expansion": after}
    STATS_FILE.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def main(step: str) -> None:
    if step == "step2":
        print(json.dumps(step2_build_base_graph(), indent=2))
    elif step == "step3":
        print(json.dumps(step3_entity_linking(), indent=2))
    elif step == "step4":
        print(json.dumps(step4_apply_predicate_alignment(), indent=2))
    elif step == "step5":
        print(json.dumps(step5_expand_q1_q2_q3(), indent=2))
    elif step == "step6":
        print(json.dumps(step6_compute_stats(), indent=2))
    else:
        raise ValueError("Unknown step. Use: step2|step3|step4|step5|step6")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Module 2 pipeline steps")
    parser.add_argument("step", help="step2|step3|step4|step5|step6")
    args = parser.parse_args()

    main(args.step)
