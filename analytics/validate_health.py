"""Does the health score catch the hidden stories, and how early? Uses ground_truth.csv (validation only).

Run:  python validate_health.py
"""
import os

import pandas as pd

import health as H

P = H.CSV
hw = pd.read_csv(os.path.join(P, "health_weekly.csv"), parse_dates=["week_start"])
gt = pd.read_csv(os.path.join(P, "ground_truth.csv"), parse_dates=["onset_date", "target_renewal"])
cu = pd.read_csv(os.path.join(P, "customers.csv"), parse_dates=["churn_date", "signup_date"])
cur = pd.read_csv(os.path.join(P, "health_current.csv"))
hw = hw.merge(gt[["customer_id", "arc", "onset_date", "saved"]], on="customer_id")
dims = [c for c in hw.columns if c.startswith("score_") and c != "score_change_4w"]

print("=== Current flags (active customers) ===")
print(cur.health_flag.value_counts().to_dict(), "| avg", round(cur.health_score.mean(), 1))
g = cur.merge(gt[["customer_id", "arc", "saved"]], on="customer_id")
print(g.groupby("arc").health_score.agg(["count", "mean", "min"]).round(1))
print(pd.crosstab(g.arc, g.health_flag))

print("\n=== Dimension means: 5 weeks before onset vs 10 weeks after (risky arcs) ===")
hw["wk"] = (hw.week_start - hw.onset_date).dt.days // 7
x = hw[hw.onset_date.notna() & ~hw.arc.isin(["false_alarm"])]
pre = x[(x.wk >= -5) & (x.wk <= -1)].groupby("arc")[dims + ["health_score"]].mean().round(0)
post = x[(x.wk >= 9) & (x.wk <= 11)].groupby("arc")[dims + ["health_score"]].mean().round(0)
print("PRE\n", pre, "\nPOST\n", post)

print("\n=== Lead time: weeks before churn that the score first went below 60 / below 70 ===")
ch = cu[cu.status == "churned"][["customer_id", "churn_date"]]
rows = []
for r in ch.itertuples():
    h = hw[hw.customer_id == r.customer_id].sort_values("week_start")
    out = {"customer_id": r.customer_id}
    for thr in (60, 70):
        b = h[h.health_score < thr]
        out[f"lead_{thr}"] = (r.churn_date - b.week_start.iloc[0]).days // 7 if len(b) else None
    rows.append(out)
lt = pd.DataFrame(rows)
print("churned:", len(lt))
for thr in (60, 70):
    c = lt[f"lead_{thr}"]
    print(f"  <{thr}: flagged before churn {c.notna().mean() * 100:.0f}% | median lead {c.median()} weeks | flagged 8+ weeks early {(c >= 8).mean() * 100:.0f}%")

print("\n=== False alarms: share of healthy and false_alarm accounts ever below 70 ===")
for arc in ["healthy_steady", "healthy_expanding", "false_alarm", "late_bloomer"]:
    a = hw[hw.arc == arc]
    print(f"  {arc:20s} customers ever <70 (after week 8 of life): "
          f"{a[a.week_start > a.groupby('customer_id').week_start.transform('min') + pd.Timedelta(weeks=8)].groupby('customer_id').health_score.min().lt(70).mean() * 100:.0f}%")
