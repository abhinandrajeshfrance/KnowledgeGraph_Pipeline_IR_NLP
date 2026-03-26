#!/usr/bin/env python3
"""
Module 6 polished demo runner (CLI) + evaluation + screenshot export.
"""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt

from pipeline import default_test_questions, load_pipeline, save_eval


def print_answer_block(result: dict) -> None:
    print("\n" + "=" * 80)
    print(f"Question: {result['question']}")
    print("-" * 80)
    print("Answer:")
    print(result["answer"])
    print("\nSupporting KG facts:")
    triples = result["supporting_triples"][:5]
    if not triples:
        print("  (none)")
    for i, t in enumerate(triples, start=1):
        print(f"  {i}. ({t['s']} -> {t['p']} -> {t['o']})")
    print("=" * 80)


def make_demo_screenshot(out_path: Path, question: str, answer: str, triples: list[dict]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["Module 6 Demo", "", f"Q: {question}", "", "A:"]
    lines.extend(textwrap.wrap(answer, width=95))
    lines.append("")
    lines.append("Evidence (top KG triples):")
    for i, t in enumerate(triples[:5], start=1):
        lines.append(f"{i}. ({t['s']} -> {t['p']} -> {t['o']})")

    text = "\n".join(lines)

    fig = plt.figure(figsize=(14, 8), dpi=150)
    fig.patch.set_facecolor("white")
    plt.axis("off")
    plt.text(0.02, 0.98, text, va="top", ha="left", fontsize=12, family="monospace")
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run polished Module 6 demo")
    parser.add_argument(
        "--question",
        type=str,
        default="Who collaborates with CNRS?",
        help="Single demo question",
    )
    parser.add_argument(
        "--eval",
        action="store_true",
        help="Run required 5-question evaluation and write rag/eval_results.json",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    pipeline = load_pipeline(root)

    print("[Module 6] Running polished KG-grounded demo...")
    answer = pipeline.answer_question(args.question)
    print_answer_block(answer)

    screenshot_path = root / "rag" / "demo_screenshot.png"
    make_demo_screenshot(
        out_path=screenshot_path,
        question=answer["question"],
        answer=answer["answer"],
        triples=answer["supporting_triples"],
    )
    print(f"[OK] Demo screenshot written: {screenshot_path}")

    if args.eval:
        questions = default_test_questions()
        eval_payload = pipeline.run_evaluation(questions)
        eval_path = root / "rag" / "eval_results.json"
        save_eval(eval_path, eval_payload)
        print(f"[OK] Evaluation written: {eval_path}")
        print(
            "[Summary] "
            f"questions={eval_payload['summary']['num_questions']}, "
            f"query_success_rate={eval_payload['summary']['kg_query_success_rate']:.2f}, "
            f"avg_supporting_triples={eval_payload['summary']['avg_supporting_triples']:.2f}"
        )


if __name__ == "__main__":
    main()
