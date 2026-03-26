import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

log_file = ROOT / "kg_artifacts" / "linking" / "wikidata_probe.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

log_file.write_text(f"START {datetime.utcnow().isoformat()}\n", encoding="utf-8")

try:
    from src.kg.module2_pipeline import _query_link_candidates

    cands = _query_link_candidates("Europe", "GPE")
    payload = {
        "time": datetime.utcnow().isoformat(),
        "candidate_count": len(cands),
        "candidates": cands[:3],
    }
    log_file.write_text("SUCCESS\n" + json.dumps(payload, indent=2), encoding="utf-8")
except Exception:
    log_file.write_text("ERROR\n" + traceback.format_exc(), encoding="utf-8")
    raise
