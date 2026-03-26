#!/usr/bin/env python3
"""Rebuild graphs and run Step 5 expansion."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from src.kg.module2_pipeline import (
        step2_build_base_graph,
        step4_apply_predicate_alignment,
        step5_expand_q1_q2_q3,
        step6_compute_stats,
    )

    print("[Pipeline] Running Step 2: Build base graph...")
    result2 = step2_build_base_graph()
    print(json.dumps(result2, indent=2))

    print("\n[Pipeline] Running Step 4: Predicate alignment...")
    result4 = step4_apply_predicate_alignment()
    print(json.dumps(result4, indent=2))

    print("\n[Pipeline] Running Step 5: Q1/Q2/Q3 expansion...")
    result5 = step5_expand_q1_q2_q3()
    print(json.dumps(result5, indent=2))

    print("\n[Pipeline] Running Step 6: Statistics...")
    result6 = step6_compute_stats()
    print(json.dumps(result6, indent=2))

except Exception as e:
    print(f"[Pipeline] Error: {e}")
    import traceback
    traceback.print_exc()
