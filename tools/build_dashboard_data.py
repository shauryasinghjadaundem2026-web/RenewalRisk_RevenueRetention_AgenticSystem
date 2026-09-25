#!/usr/bin/env python3
"""
Build dashboard-data.json from the pipeline's full output.

agents/orchestrator.py writes output/dashboard_data_full.json with every
field for every account. This script derives a few convenience fields
or view for the dashboards (this HTML page and the standalone one) and
writes dashboard-data.json -- the file dashboard.html / index.html
actually read.

Run this after agents/orchestrator.py whenever the underlying data or
model changes, then rebuild the standalone page:

    python3 agents/orchestrator.py
    python3 tools/build_dashboard_data.py
    python3 tools/build_index.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "output" / "dashboard_data_full.json"
OUT = ROOT / "dashboard-data.json"


def enrich(rec):
    """Add the flat cost/revenue/action fields the dashboard tables read,
    derived from the recommended option -- without dropping the full
    options list, policy clause text or routing reason the Agent console
    needs to replay this account step by step."""
    options = rec.get("options") or []
    recommended = rec.get("recommended_option")
    chosen = next((o for o in options if o.get("option") == recommended), None)
    rec = dict(rec)
    rec["action_label"] = (chosen or {}).get("label") or (recommended or "Monitor / no action")
    rec["cost"] = (chosen or {}).get("cost", 0.0)
    rec["revenue_saved"] = (chosen or {}).get("revenue_saved", 0.0)
    rec["net_benefit"] = (chosen or {}).get("net_benefit", 0.0)
    rec["roi"] = (chosen or {}).get("roi", 0.0)
    # route/decision_ts are implied by which list (escalation_queue vs
    # autonomous_log) the record lives in -- the dashboards derive this
    # client-side rather than trusting a stored field.
    rec.pop("route", None)
    rec.pop("decision_ts", None)
    return rec


def main():
    if not SRC.exists():
        sys.exit(f"build_dashboard_data.py: {SRC} not found -- run agents/orchestrator.py first")

    full = json.loads(SRC.read_text(encoding="utf-8"))

    out = dict(full)
    out["escalation_queue"] = [enrich(r) for r in full["escalation_queue"]]
    out["autonomous_log"] = [enrich(r) for r in full["autonomous_log"]]
    out.pop("all_decisions_count", None)

    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes) -- "
          f"{len(out['escalation_queue'])} escalated + {len(out['autonomous_log'])} autonomous accounts")


if __name__ == "__main__":
    main()
