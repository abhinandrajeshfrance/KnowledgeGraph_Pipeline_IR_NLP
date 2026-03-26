#!/usr/bin/env python3

from pathlib import Path

from src.rag.module6_rag import run_rag_demo, save_demo_output


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    query = "Which organizations collaborate in knowledge graphs and where are they located?"

    result = run_rag_demo(root=root, query=query)
    out_path = save_demo_output(root=root, result=result)

    print("[Module 6] RAG demo complete")
    print(f"  Query: {result['query']}")
    print(f"  Retrieved docs: {len(result['retrieved_documents'])}")
    print(f"  Retrieved KG triples: {len(result['retrieved_kg_triples'])}")
    print(f"  Output file: {out_path}")
