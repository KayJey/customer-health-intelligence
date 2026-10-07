"""Sanity checks: does the synthetic data actually show the story arcs we built in?

Run:  python validate.py
"""
import os
import pandas as pd

P = os.path.join(os.path.dirname(__file__), "..", "data", "csv")
r = lambda n: pd.read_csv(os.path.join(P, f"{n}.csv"))
cu, gt, us = r("customers"), r("ground_truth"), r("weekly_usage")
tk, em, pr, mi, doc = r("tickets"), r("email_events"), r("play_runs"), r("onboarding_milestones"), r("documents")
cu = cu.merge(gt, on="customer_id")
us = us.merge(gt[["customer_id", "arc"]], on="customer_id")
tk = tk.merge(gt[["customer_id", "arc"]], on="customer_id")
em = em.merge(gt[["customer_id", "arc"]], on="customer_id")

print("=== Customers ===")
print(cu.status.value_counts().to_dict(), "| churn rate", round((cu.status == "churned").mean() * 100, 1), "%")
print(cu.size_band.value_counts().to_dict(), cu.tier.value_counts().to_dict())
print(cu.lifecycle_stage.value_counts().to_dict())

print("\n=== Churn and rescue by arc ===")
g = cu.groupby("arc").agg(n=("customer_id", "count"), churned=("status", lambda s: (s == "churned").sum()),
                          saved=("saved", "sum"))
print(g)

print("\n=== Seat utilisation: 5 weeks before vs 8-12 weeks after story onset ===")
u = us.merge(gt[["customer_id", "onset_date"]], on="customer_id", suffixes=("", "_gt"))
u["week_start"] = pd.to_datetime(u.week_start)
u["onset_date"] = pd.to_datetime(u.onset_date)
u = u[u.onset_date.notna()].copy()
u["wk"] = (u.week_start - u.onset_date).dt.days // 7
pre = u[(u.wk >= -5) & (u.wk <= -1)].groupby("arc").seat_utilisation.mean()
post = u[(u.wk >= 8) & (u.wk <= 12)].groupby("arc").seat_utilisation.mean()
print(pd.DataFrame({"pre": pre.round(2), "post_8_12w": post.round(2)}))
risky = cu[(cu.status == "active") & cu.onset_date.notna() & ~cu.saved & (cu.arc != "false_alarm")]
print("\nstill active, story underway, not saved (the at-risk pool):", len(risky), "customers, ARR $", int(risky.arr_current.sum()))

print("\n=== Tickets per customer, reopen rate, escalation rate, first response (h) by arc ===")
t = tk.groupby("arc").agg(tickets=("ticket_id", "count"), reopen=("reopen_count", lambda s: (s > 0).mean()),
                          esc=("escalated", "mean"), frh=("first_response_hours", "median"))
t["per_customer"] = t.tickets / gt.arc.value_counts()
print(t.round(2))

print("\n=== Email open rate by arc (non-bounced) ===")
print(em[~em.bounced].groupby("arc").opened.mean().round(2).to_dict())
print("bounced emails (departed champion):", int(em.bounced.sum()), "across", em[em.bounced].customer_id.nunique(), "customers")

print("\n=== Time to first value (signup to shared) by size band ===")
sh = mi[mi.milestone == "shared_by_second_user"].merge(cu[["customer_id", "size_band"]], on="customer_id")
print(sh.groupby("size_band").days_from_signup.median().to_dict())
print("customers reaching first value:", sh.customer_id.nunique(), "of", len(cu))

print("\n=== Play experiment: feature utilisation change 4 weeks after play ===")
done = pr[pr.outcome != "pending"]
print(done.groupby(["play_id", "experiment_group", "variant"]).agg(n=("run_id", "count"), mean_delta=("delta_4w", "mean"),
                                               improved=("outcome", lambda s: (s == "improved").mean())).round(3))

print("\n=== Documents by type ===")
print(doc.doc_type.value_counts().to_dict())
print("\n--- sample: competitor mentions ---")
m = doc[doc.text.str.contains("Brightlane|Datavista|Pivotly|Clearmetric", regex=True)]
print(len(m), "docs mention a competitor;", m.customer_id.nunique(), "customers")
print(m.merge(gt, on="customer_id").arc.value_counts().to_dict())
print("\n--- sample ticket ---")
print(doc[doc.doc_type == "ticket_thread"].iloc[3].text)
print("\n--- sample CSM note (critical champion loss) ---")
s = doc[(doc.doc_type == "call_note")].merge(gt, on="customer_id")
print(s[s.arc == "champion_loss"].iloc[-1].text)
