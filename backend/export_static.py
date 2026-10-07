"""Export every API response the dashboard needs to static JSON files, so the app can be hosted with no backend.

Run:  python export_static.py        (writes ../dashboard/public/static-api/)
Then build the dashboard in static mode:  cd ../dashboard && npm run build:static
"""
import json
import shutil
from pathlib import Path

import demo_copilot
import queries as Q
import tools as T
from db import ROOT, q

OUT = ROOT / "dashboard" / "public" / "static-api"


def dump(rel, data):
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, default=str, separators=(",", ":")), encoding="utf-8")


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    dump("overview.json", Q.overview())
    dump("customers.json", Q.customers(sort="customer_id", limit=1000))      # filtered in the browser
    dump("cohorts.json", Q.cohorts())
    dump("rfm.json", Q.rfm(None))                                             # segment filter happens in the browser
    dump("plays.json", Q.plays())
    dump("alerts.json", Q.alerts())
    dump("program-impact.json", Q.program_impact())
    dump("copilot_tools.json", T.catalog())
    entries = demo_copilot.load()
    dump("copilot_demo.json", entries)
    ids = [r["customer_id"] for r in q("SELECT customer_id FROM customers ORDER BY customer_id")]
    drafts = 0
    for cid in ids:
        dump(f"customer/{cid}.json", Q.customer_detail(cid))
        try:
            d = demo_copilot.template_draft(cid)
            if "error" not in d:
                dump(f"drafts/{cid}.json", d)
                drafts += 1
        except Exception:
            pass   # churned customers have no recommendation or draft
    size = sum(f.stat().st_size for f in OUT.rglob("*.json"))
    print(f"exported {len(ids)} customers, {drafts} drafts, {len(entries)} recorded copilot answers, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
