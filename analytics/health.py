"""Customer health score: five dimensions, scored 0-100 per customer per week.

Transparent on purpose: every number can be traced to raw signals, and CS can see which
dimension pulled a score down. A churn model (later) is meant to sit next to this, not replace it.

Dimensions and weights
  adoption    30%  seat utilisation, usage trend, feature depth
  support     20%  escalations, reopened tickets, slow first response, stale open tickets (last 8 weeks)
  engagement  20%  email open rate, champion present, latest NPS
  commercial  20%  payment lateness, disputes, contraction or expansion, exec sponsor present
  onboarding  10%  milestones reached, time to first value

Score = 0.8 x weighted average + 0.2 x weakest dimension, so one very weak area cannot be averaged away.
Flag:  >= 75 Healthy | 60-74 Watch | < 60 At risk
Text signals (competitor mentions) are tagged as drivers but NOT scored: they are noisy, and
the copilot is meant to read them in context.
"""
import os
from datetime import timedelta

import numpy as np
import pandas as pd

CSV = os.path.join(os.path.dirname(__file__), "..", "data", "csv")
WEIGHTS = {"adoption": 0.30, "support": 0.20, "engagement": 0.20, "commercial": 0.20, "onboarding": 0.10}
SLA_HOURS = {"CSM-led": 4, "Pooled": 8, "Digital": 12}
COMPETITORS = ("Brightlane BI", "Datavista", "Pivotly", "Clearmetric")


def clip(x, lo=0.0, hi=100.0):
    return float(max(lo, min(hi, x)))


def load():
    r = lambda n, **k: pd.read_csv(os.path.join(CSV, f"{n}.csv"), **k)
    d = dict(
        cu=r("customers", parse_dates=["signup_date", "churn_date", "next_renewal_date"]),
        co=r("contacts", parse_dates=["joined_date", "left_date"]),
        us=r("weekly_usage", parse_dates=["week_start"]),
        mi=r("onboarding_milestones", parse_dates=["milestone_date"]),
        tk=r("tickets", parse_dates=["created_at", "resolved_at"]),
        em=r("email_events", parse_dates=["sent_at", "opened_at"]),
        nps=r("nps_responses", parse_dates=["survey_date"]),
        inv=r("invoices", parse_dates=["invoice_date", "due_date", "paid_date"]),
        ev=r("contract_events", parse_dates=["event_date"]),
        doc=r("documents", parse_dates=["doc_date"]),
    )
    return d


def _by(df, col="customer_id"):
    return {k: v.reset_index(drop=True) for k, v in df.groupby(col)}


def score_all(d):
    cu = d["cu"].set_index("customer_id")
    us, mi, tk, em, nps, inv, ev, co = (_by(d[k]) for k in ["us", "mi", "tk", "em", "nps", "inv", "ev", "co"])
    comp_docs = d["doc"][d["doc"].text.str.contains("|".join(COMPETITORS), regex=True)]
    comp_by = _by(comp_docs)
    empty = pd.DataFrame()
    rows = []
    for cid, u in us.items():
        c = cu.loc[cid]
        tier, band, signup = c.tier, c.size_band, c.signup_date
        mil, tks, ems, nps_c, invs, evs, cts = (x.get(cid, empty) for x in (mi, tk, em, nps, inv, ev, co))
        cdocs = comp_by.get(cid, empty)
        util = u.seat_utilisation.to_numpy()
        for i, row in enumerate(u.itertuples()):
            we = row.week_start + timedelta(days=6)
            tags = []

            # ---- adoption
            util_s = clip(row.seat_utilisation / 0.6 * 100)
            last2 = util[max(0, i - 1):i + 1].mean()
            prev = util[max(0, i - 5):i - 1].mean() if i >= 3 else None
            trend = 50.0 if prev is None or prev < 0.05 else clip(50 + (last2 / prev - 1) * 150)
            depth = clip(row.features_used / 8 * 100)
            adoption = 0.5 * util_s + 0.25 * trend + 0.25 * depth
            peak = util[max(0, i - 12):i + 1].max()
            if peak > 0.2 and row.seat_utilisation < 0.65 * peak and i >= 6:
                tags.append(f"usage_down_{int((1 - row.seat_utilisation / peak) * 100)}pct")

            # ---- onboarding
            age = (we - signup).days
            done = mil[mil.milestone_date <= we] if len(mil) else empty
            names = set(done.milestone) if len(done) else set()
            if "shared_by_second_user" in names:
                ttfv = int(done[done.milestone == "shared_by_second_user"].days_from_signup.iloc[0])
                onboarding = 100.0 if ttfv <= 45 else 85.0
            elif age <= 14:
                onboarding = 70.0
            else:
                onboarding = (len(names) / 4 * 100) * max(0.3, 1 - max(0, age - 21) / 90)
            if age >= 28 and "shared_by_second_user" not in names:
                tags.append("stalled_onboarding")

            # ---- support (last 8 weeks)
            esc = reop = slow = stale = n_t = 0
            if len(tks):
                t8 = tks[(tks.created_at.dt.normalize() > we - timedelta(days=56)) & (tks.created_at.dt.normalize() <= we)]
                n_t = len(t8)
                esc = int(t8.escalated.sum())
                reop = int((t8.reopen_count > 0).sum())
                slow = int((t8.first_response_hours > SLA_HOURS[tier] * 2).sum())
                tk_open = tks[(tks.created_at.dt.normalize() <= we) & (tks.resolved_at.isna() | (tks.resolved_at.dt.normalize() > we))]
                stale = int((tk_open.created_at.dt.normalize() < we - timedelta(days=7)).sum())
            support = clip(100 - 20 * esc - 12 * reop - 8 * slow - 10 * stale - 2 * max(0, n_t - 3))
            if esc:
                tags.append("escalation")
            if reop >= 2:
                tags.append("tickets_reopened")
            if slow >= 2:
                tags.append("slow_support")

            # ---- engagement
            e8 = ems[(ems.sent_at.dt.normalize() > we - timedelta(days=56)) & (ems.sent_at.dt.normalize() <= we)] if len(ems) else empty
            good = e8[~e8.bounced] if len(e8) else empty
            if len(good) >= 2:
                open_rate = good.opened.mean()
                email_s = clip((open_rate - 0.1) / 0.4 * 100)
                if len(good) >= 3 and open_rate < 0.2:
                    tags.append("emails_ignored")
            else:
                email_s = 60.0
            ch = cts[cts.is_champion] if len(cts) else empty
            act = ch[(ch.joined_date <= we) & (ch.left_date.isna() | (ch.left_date > we))] if len(ch) else empty
            if len(act):
                champ_s = 100.0
            else:
                gone = ch[(ch.left_date <= we)]
                gap = (we - gone.left_date.max()).days if len(gone) else 0
                champ_s = 25.0 if gap <= 30 else 0.0
                tags.append("champion_left")
            if len(e8) and e8.bounced.sum() >= 1:
                champ_s = min(champ_s, 10.0)
            if len(nps_c):
                n_recent = nps_c[(nps_c.survey_date <= we) & (nps_c.survey_date > we - timedelta(days=180))]
                nps_s = float(n_recent.sort_values("survey_date").score.iloc[-1] * 10) if len(n_recent) else 60.0
            else:
                nps_s = 60.0
            engagement = 0.30 * email_s + 0.45 * champ_s + 0.25 * nps_s

            # ---- commercial and relationship
            late_avg = 0.0
            disputed = False
            if len(invs):
                iv = invs[invs.invoice_date <= we].tail(3)
                if len(iv):
                    lates = []
                    for r_ in iv.itertuples():
                        if pd.notna(r_.paid_date) and r_.paid_date <= we:
                            lates.append(r_.days_late)
                        elif r_.due_date < we:
                            lates.append((we - r_.due_date).days)
                        else:
                            lates.append(0)
                    late_avg = float(np.mean(lates))
                    disputed = bool(iv[iv.invoice_date > we - timedelta(days=90)].disputed.any())
            commercial = clip(100 - late_avg * 5, 20, 100)
            if late_avg > 7:
                tags.append("late_payments")
            if disputed:
                commercial -= 25
                tags.append("invoice_disputed")
            if len(evs):
                recent = evs[(evs.event_date <= we) & (evs.event_date > we - timedelta(days=180))]
                if (recent.event_type == "contraction").any():
                    commercial -= 15
                if (recent.event_type == "expansion").any():
                    commercial += 10
            if band != "SME" and len(cts):
                sp = cts[cts.is_exec_sponsor]
                if len(sp) and not len(sp[(sp.joined_date <= we) & (sp.left_date.isna() | (sp.left_date > we))]):
                    commercial -= 15
            commercial = clip(commercial)

            if len(cdocs) and (cdocs.doc_date.between(we - timedelta(days=90), we)).any():
                tags.append("competitor_mentioned")

            dims = dict(adoption=adoption, support=support, engagement=engagement, commercial=commercial, onboarding=onboarding)
            weighted = sum(WEIGHTS[k] * v for k, v in dims.items())
            score = 0.8 * weighted + 0.2 * min(dims.values())   # weakest-link blend
            top = max(WEIGHTS, key=lambda k: WEIGHTS[k] * (100 - dims[k]))
            rows.append(dict(customer_id=cid, week_start=row.week_start, **{f"score_{k}": round(v, 1) for k, v in dims.items()},
                             health_score=round(score, 1),
                             health_flag="At risk" if score < 60 else "Watch" if score < 75 else "Healthy",
                             top_driver=top, driver_tags=";".join(tags)))
    out = pd.DataFrame(rows).sort_values(["customer_id", "week_start"]).reset_index(drop=True)
    out["score_change_4w"] = out.groupby("customer_id").health_score.diff(4).round(1)
    return out
