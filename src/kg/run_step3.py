import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

LINK_DIR = ROOT / "kg_artifacts" / "linking"
LINK_DIR.mkdir(parents=True, exist_ok=True)
log_file = LINK_DIR / "step3_run.log"
log_file.write_text("STARTED\n", encoding="utf-8")

try:
    from src.kg.module2_pipeline import step3_entity_linking

    result = step3_entity_linking()
    log_file.write_text("SUCCESS\n" + json.dumps(result, indent=2), encoding="utf-8")
except Exception:
    log_file.write_text("ERROR\n" + traceback.format_exc(), encoding="utf-8")
    raise
