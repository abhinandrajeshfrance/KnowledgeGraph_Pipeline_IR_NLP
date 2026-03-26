#!/usr/bin/env python3
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from src.kg.module2_pipeline import step3_entity_linking
    
    print("[Test] Starting Step 3 entity linking...")
    result = step3_entity_linking()
    print("[Test] SUCCESS!")
    print(f"Result: {result}")
except Exception as e:
    print(f"[Test] ERROR: {e}")
    traceback.print_exc()
