"""Cohort analysis (size, tier, signup quarter) and usage-based RFM segmentation.

RFM is adapted for SaaS (there are no purchases to count):
  Recency   days since the last week with meaningful use (>= 25% of seats and >= 50% of the customer's own typical level)
  Frequency average sessions per licensed seat per week over the last 8 weeks
  Monetary  current ARR
Each is scored 1-5; segments are rules on those scores.
"""
import numpy as np
import pandas as pd

START = pd.Timestamp("2025-10-06")
SNAPSHOT = pd.Timestamp("2026-10-05")
MEANINGFUL_USE = 0.25


def arr_at(ev, cid, d):
    e = ev[(ev.customer_id == cid) & (ev.event_date <= d)]
    return float(e.arr_delta.sum())


def size_and_tier_cohorts(d, cur):
    cu, ev, mi = d["cu"], d["ev"], d["mi"]
    ttfv = mi[mi.milestone == "shared_by_second_user"].set_index("customer_id").days_from_signup
    base = cu[cu.signup_date < START].copy()       # customers present at the start of the window
    base["arr_start"] = [arr_at(ev, c, START) for c in base.customer_id]
    out = {}
    for col, name in [("size_band", "size"), ("tier", "tier")]:
        rows = []
        for key, g in cu.groupby(col):
            act = g[g.status == "active"]
            cc = cur[cur[col] == key]
            b = base[base[col] == key]
            arr_now = b.arr_current.sum()
            rows.append({col: key, "customers": len(g), "active": len(act),
                         "avg_health": round(cc.health_score.mean(), 1), "at_risk": int((cc.health_flag == "At risk").sum()),
                         "arr_at_risk": round(cc[cc.health_flag == "At risk"].arr_current.sum()),
                         "arr_total": round(act.arr_current.sum()),
                         "logo_retention_pct": round((b.status == "active").mean() * 100, 1) if len(b) else None,
                         "gross_retention_pct": round(np.minimum(b.arr_current, b.arr_start).sum() / b.arr_start.sum() * 100, 1) if len(b) else None,
                         "net_retention_pct": round(arr_now / b.arr_start.sum() * 100, 1) if len(b) else None,
                         "median_days_to_first_value": float(ttfv.reindex(g.customer_id).median()),
                         "avg_seat_utilisation": round(cc.seat_utilisation.mean(), 3)})
        out[name] = pd.DataFrame(rows)
    return out


def signup_quarter_cohorts(d, cur):
    cu = d["cu"].copy()
    cu["cohort"] = cu.signup_date.dt.year.astype(str) + "-Q" + cu.signup_date.dt.quarter.astype(str)
    cu["age_m"] = (SNAPSHOT - cu.signup_date).dt.days / 30.4
    cu["churn_age_m"] = (cu.churn_date - cu.signup_date).dt.days / 30.4
    cu["churn_age_m"] = cu.churn_age_m.fillna(np.inf)
    rows, mat = [], []
    for k, g in cu.groupby("cohort"):
        cc = cur[cur.customer_id.isin(g.customer_id)]
        rows.append({"cohort": k, "customers": len(g), "active": int((g.status == "active").sum()),
                     "logo_retention_pct": round((g.status == "active").mean() * 100, 1),
                     "avg_health": round(cc.health_score.mean(), 1), "at_risk": int((cc.health_flag == "At risk").sum())})
        m = {"cohort": k, "customers": len(g)}
        for months in (3, 6, 9, 12, 15, 18):
            elig = g[g.age_m >= months]
            # only show a cell when the whole cohort has been observed that long
            m[f"M{months}"] = round((elig.churn_age_m > months + 0.1).mean() * 100, 1) if len(elig) == len(g) else None
        mat.append(m)
    return pd.DataFrame(rows), pd.DataFrame(mat)


def rfm(d, cur):
    us, cu = d["us"], d["cu"]
    act = cu[cu.status == "active"].set_index("customer_id")
    last = us.sort_values("week_start").groupby("customer_id")
    rec, freq = {}, {}
    for cid, g in last:
        if cid not in act.index:
            continue
        # meaningful use = at least 25% of seats AND at least 50% of the customer's own typical (p90) level
        thr = max(MEANINGFUL_USE, 0.5 * g.seat_utilisation.quantile(0.9))
        ok = g[g.seat_utilisation >= thr]
        rec[cid] = (SNAPSHOT - (ok.week_start.max() + pd.Timedelta(days=6))).days if len(ok) else 999
        t8 = g.tail(8)
        freq[cid] = float((t8.sessions / t8.seats_licensed.clip(lower=1)).mean())
    df = pd.DataFrame({"recency_days": pd.Series(rec).clip(lower=0), "frequency": pd.Series(freq)})
    df["monetary_arr"] = act.arr_current.reindex(df.index)
    df["age_days"] = (SNAPSHOT - act.signup_date.reindex(df.index)).dt.days
    df["R"] = pd.cut(df.recency_days, [-1, 14, 28, 56, 90, 10_000], labels=[5, 4, 3, 2, 1]).astype(int)
    df["F"] = pd.qcut(df.frequency.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    df["M"] = pd.qcut(df.monetary_arr.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)

    def seg(r):
        if r.R <= 2 and r.M >= 4:
            return "Cannot lose"          # high ARR, gone quiet
        if r.R <= 2 and r.F >= 3:
            return "At risk"              # used to be active, now lapsing
        if r.R <= 2:
            return "Hibernating"
        if r.age_days < 120 and r.R >= 4:
            return "Promising"            # new and ramping
        if r.R >= 4 and r.F >= 4:
            return "Champions"
        if r.R >= 3 and r.F >= 3:
            return "Loyal"
        if r.R >= 4:
            return "Light users"          # recent but low frequency
        return "Need attention"           # R = 3, slipping
    df["rfm_segment"] = df.apply(seg, axis=1)
    df.index.name = "customer_id"
    df = df.reset_index()
    summ = df.groupby("rfm_segment").agg(customers=("customer_id", "count"), arr=("monetary_arr", "sum")).reset_index()
    summ["arr"] = summ.arr.round()
    return df, summ.sort_values("customers", ascending=False)
