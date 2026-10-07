"""Compute health scores, cohorts and RFM, write them next to the raw CSVs, and build a local SQLite db.

Run:  python run_analytics.py     (after generator/generate.py)
Outputs in data/csv: health_weekly, health_current, cohort_size, cohort_tier, cohort_signup_quarter,
cohort_retention_matrix, rfm_customers, rfm_summary, portfolio_kpis.  Also data/health.db (SQLite).
"""
import os
import sqlite3
import sys

import pandas as pd

import cohorts as C
import health as H

OUT = H.CSV


def main():
    d = H.load()
    print("scoring weekly health...")
    hw = H.score_all(d)
    # how many consecutive weeks the customer has been in its current flag (for alert persistence rules)
    grp = (hw.health_flag != hw.groupby("customer_id").health_flag.shift()).cumsum()
    hw["weeks_in_flag"] = hw.groupby(grp).cumcount() + 1
    hw.to_csv(os.path.join(OUT, "health_weekly.csv"), index=False)

    cu = d["cu"]
    latest = hw.sort_values("week_start").groupby("customer_id").tail(1)
    cur = cu[cu.status == "active"].merge(latest, on="customer_id", how="left")
    cur = cur.merge(d["us"].sort_values("week_start").groupby("customer_id").tail(1)[["customer_id", "seat_utilisation", "active_users"]],
                    on="customer_id", how="left")
    cur["days_to_renewal"] = (cur.next_renewal_date - C.SNAPSHOT).dt.days

    rf, rf_sum = C.rfm(d, cur)
    cur = cur.merge(rf[["customer_id", "R", "F", "M", "rfm_segment"]], on="customer_id", how="left")
    cols = ["customer_id", "company_name", "industry", "size_band", "tier", "lifecycle_stage", "arr_current", "next_renewal_date",
            "days_to_renewal", "seat_utilisation", "active_users", "health_score", "health_flag", "score_change_4w", "score_adoption",
            "weeks_in_flag", "score_support", "score_engagement", "score_commercial", "score_onboarding", "top_driver", "driver_tags", "R", "F", "M",
            "rfm_segment"]
    cur[cols].to_csv(os.path.join(OUT, "health_current.csv"), index=False)

    co = C.size_and_tier_cohorts(d, cur)
    co["size"].to_csv(os.path.join(OUT, "cohort_size.csv"), index=False)
    co["tier"].to_csv(os.path.join(OUT, "cohort_tier.csv"), index=False)
    q, qm = C.signup_quarter_cohorts(d, cur)
    q.to_csv(os.path.join(OUT, "cohort_signup_quarter.csv"), index=False)
    qm.to_csv(os.path.join(OUT, "cohort_retention_matrix.csv"), index=False)
    rf.to_csv(os.path.join(OUT, "rfm_customers.csv"), index=False)
    rf_sum.to_csv(os.path.join(OUT, "rfm_summary.csv"), index=False)

    ar = cur[cur.health_flag == "At risk"]
    base = cu[cu.signup_date < C.START]
    ttfv = d["mi"][d["mi"].milestone == "shared_by_second_user"].days_from_signup.median()
    kpi = pd.DataFrame([{
        "active_customers": len(cur), "avg_health": round(cur.health_score.mean(), 1), "at_risk_customers": len(ar),
        "arr_at_risk": round(ar.arr_current.sum()), "total_arr": round(cur.arr_current.sum()),
        "median_days_to_first_value": float(ttfv),
        "logo_retention_pct": round((base.status == "active").mean() * 100, 1),
        "expansion_candidates": int((cur.seat_utilisation > 0.85).sum()),
        "snapshot_date": C.SNAPSHOT.date().isoformat()}])
    kpi.to_csv(os.path.join(OUT, "portfolio_kpis.csv"), index=False)
    print(kpi.T.to_string(header=False))

    # local SQLite for the app
    db = os.path.join(OUT, "..", "health.db")
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    for f in sorted(os.listdir(OUT)):
        if f.endswith(".csv") and f != "ground_truth.csv":
            pd.read_csv(os.path.join(OUT, f)).to_sql(f[:-4], con, index=False)
    for t, col in [("weekly_usage", "customer_id"), ("tickets", "customer_id"), ("health_weekly", "customer_id"),
                   ("documents", "customer_id"), ("email_events", "customer_id")]:
        con.execute(f"CREATE INDEX idx_{t} ON {t}({col})")
    con.commit()
    con.close()
    print("\nwrote SQLite:", os.path.abspath(db))


if __name__ == "__main__":
    sys.exit(main())
