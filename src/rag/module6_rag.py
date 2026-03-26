from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class Chunk:
    doc: str
    text: str


def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_documents(extracted_dir: Path) -> List[tuple[str, str]]:
    docs: List[tuple[str, str]] = []
    for path in sorted(extracted_dir.glob("*.txt")):
        content = path.read_text(encoding="utf-8", errors="ignore")
        if content.strip():
            docs.append((path.name, content))
    return docs


def chunk_text(text: str, chunk_size: int = 700, overlap: int = 120) -> List[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []

    chunks = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end])
        if end == len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def build_chunks(extracted_dir: Path) -> List[Chunk]:
    chunks: List[Chunk] = []
    for name, text in load_documents(extracted_dir):
        for piece in chunk_text(text):
            chunks.append(Chunk(doc=name, text=piece))
    return chunks


def retrieve(chunks: List[Chunk], query: str, top_k: int = 4) -> List[dict]:
    if not chunks:
        return []

    corpus = [c.text for c in chunks]
    vect = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    mat = vect.fit_transform(corpus)
    q = vect.transform([query])
    scores = cosine_similarity(q, mat).ravel()

    idx = scores.argsort()[::-1][:top_k]
    out = []
    for i in idx:
        out.append(
            {
                "document": chunks[int(i)].doc,
                "score": float(scores[int(i)]),
                "text": chunks[int(i)].text,
            }
        )
    return out


def load_kg_triples(path: Path) -> List[tuple[str, str, str]]:
    triples = []
    if not path.exists():
        return triples
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3:
                triples.append((parts[0], parts[1], parts[2]))
    return triples


def retrieve_kg_context(query: str, triples: List[tuple[str, str, str]], top_k: int = 8) -> List[dict]:
    q = normalize(query)
    terms = set(q.split())
    scored = []

    for h, r, t in triples:
        h_n = normalize(h.replace("_", " "))
        r_n = normalize(r.replace("_", " "))
        t_n = normalize(t.replace("_", " "))
        text = f"{h_n} {r_n} {t_n}"
        score = sum(1 for tok in terms if tok and tok in text)
        if score > 0:
            scored.append((score, h, r, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, h, r, t in scored[:top_k]:
        out.append({"score": score, "triple": [h, r, t]})
    return out


def compose_answer(query: str, top_docs: List[dict], kg_hits: List[dict]) -> str:
    lines = [f"Query: {query}", "", "Evidence from retrieved documents:"]
    for i, d in enumerate(top_docs, start=1):
        snippet = d["text"][:260].strip()
        lines.append(f"{i}. [{d['document']}] score={d['score']:.4f} :: {snippet}")

    lines.append("")
    lines.append("Evidence from KG triples:")
    if kg_hits:
        for i, item in enumerate(kg_hits, start=1):
            h, r, t = item["triple"]
            lines.append(f"{i}. ({h}, {r}, {t})")
    else:
        lines.append("No high-overlap KG triples found for this query.")

    lines.append("")
    lines.append("Draft answer:")
    lines.append(
        "The response should cite the retrieved passages and the KG relations above. "
        "Use the highest-score document chunks as primary support and KG triples as structured evidence."
    )
    return "\n".join(lines)


def run_rag_demo(root: Path, query: str) -> dict:
    extracted_dir = root / "_extracted_text"
    kge_train = root / "data" / "kge" / "train.txt"

    chunks = build_chunks(extracted_dir)
    top_docs = retrieve(chunks, query, top_k=4)
    triples = load_kg_triples(kge_train)
    kg_hits = retrieve_kg_context(query, triples, top_k=8)
    answer = compose_answer(query, top_docs, kg_hits)

    result = {
        "query": query,
        "retrieved_documents": top_docs,
        "retrieved_kg_triples": kg_hits,
        "answer": answer,
        "stats": {
            "num_chunks": len(chunks),
            "num_kg_triples": len(triples),
        },
    }
    return result


def save_demo_output(root: Path, result: dict) -> Path:
    out_dir = root / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "module6_rag_demo.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return out_path
