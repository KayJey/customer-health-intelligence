"""Data functions behind the dashboard API. Plain SQL over health.db, no AI."""
from db import LATEST_WEEK, SNAPSHOT, q, q1

PLAY_FOR_TAG = [
    ("champion_left", "champion_loss", "Champion left: introduce yourself to the new owner and offer a walkthrough"),
    ("escalation", "support_recovery", "Open escalation: assign a named support owner and share a root-cause update"),
    ("tickets_reopened", "support_recovery", "Tickets keep reopening: assign a named support owner and share a root-cause update"),
    ("stalled_onboarding", "onboarding_stall", "Onboarding stalled: send a guided first-dashboard plan"),
    ("usage_down", "adoption_nudge", "Usage falling: send a personalised adoption nudge"),
]


def recommend(c):
    """Rule-based next action for one health_current row (dict). Deterministic and explainable."""
    tags = (c.get("driver_tags") or "").split(";")
    if c["health_flag"] == "At risk" and c["tier"] != "CSM-led" and (c["arr_current"] or 0) >= 25000:
        return {"action": "Move to CSM-led", "play": "handoff", "why": "At risk with meaningful ARR in a digital-led tier"}
    for tag, play, why in PLAY_FOR_TAG:
        if any(t.startswith(tag) for t in tags):
            return {"action": play.replace("_", " ").title(), "play": play, "why": why}
    if c.get("days_to_renewal") is not None and c["days_to_renewal"] <= 120 and c["health_flag"] != "Healthy":
        return {"action": "Renewal readiness", "play": "renewal_readiness", "why": "Renewal within 120 days and not healthy"}
    if (c.get("seat_utilisation") or 0) > 0.85:
        return {"action": "Share expansion signal", "play": "expansion_signal", "why": "Seat use above 85%"}
    return {"action": "Monitor", "play": None, "why": "No action needed"}


def overview():
    kpi = q1("SELECT * FROM portfolio_kpis")
    prev_week = q1("SELECT week_start FROM (SELECT DISTINCT week_start FROM health_weekly ORDER BY week_start DESC LIMIT 5) ORDER BY week_start LIMIT 1")["week_start"]
    prev = q1("""SELECT ROUND(AVG(health_score),1) avg_health, SUM(health_flag='At risk') at_risk
                 FROM health_weekly WHERE week_start=? AND customer_id IN (SELECT customer_id FROM customers WHERE status='active')""",
              (prev_week,))
    dist = q("SELECT health_flag, COUNT(*) n, ROUND(SUM(arr_current)) arr FROM health_current GROUP BY health_flag")
    trend = q("""SELECT week_start, ROUND(AVG(health_score),1) avg_health,
                 ROUND(100.0*AVG(health_flag='At risk'),1) pct_at_risk, COUNT(*) customers
                 FROM health_weekly GROUP BY week_start ORDER BY week_start""")
    movers = q("""SELECT customer_id, company_name, tier, size_band, arr_current, health_score, score_change_4w, top_driver, driver_tags
                  FROM health_current WHERE score_change_4w IS NOT NULL ORDER BY ABS(score_change_4w) DESC LIMIT 8""")
    return {"snapshot": SNAPSHOT, "kpis": kpi,
            "vs_4_weeks_ago": {"avg_health": prev["avg_health"], "at_risk": prev["at_risk"]},
            "distribution": dist, "trend": trend, "movers": movers}


def customers(tier=None, stage=None, industry=None, band=None, flag=None, renewal_within=None, search=None,
              sort="health_score", order="asc", limit=100):
    where, p = ["1=1"], []
    for col, val in [("tier", tier), ("lifecycle_stage", stage), ("industry", industry), ("size_band", band), ("health_flag", flag)]:
        if val:
            where.append(f"{col}=?")
            p.append(val)
    if renewal_within:
        where.append("days_to_renewal<=?")
        p.append(int(renewal_within))
    if search:
        where.append("(customer_id LIKE ? OR company_name LIKE ?)")
        p += [f"%{search}%", f"%{search}%"]
    sort = sort if sort in {"health_score", "arr_current", "days_to_renewal", "score_change_4w", "customer_id"} else "health_score"
    order = "DESC" if str(order).lower() == "desc" else "ASC"
    rows = q(f"""SELECT customer_id, company_name, industry, size_band, tier, lifecycle_stage, arr_current, next_renewal_date,
                 days_to_renewal, seat_utilisation, health_score, health_flag, score_change_4w, weeks_in_flag, top_driver,
                 driver_tags, rfm_segment FROM health_current WHERE {' AND '.join(where)}
                 ORDER BY {sort} {order} LIMIT ?""", (*p, int(limit)))
    return {"count": len(rows), "customers": rows}


def customer_detail(cid):
    cur = q1("SELECT * FROM health_current WHERE customer_id=?", (cid,))
    cust = q1("SELECT * FROM customers WHERE customer_id=?", (cid,))
    if not cust:
        return None
    hist = q("""SELECT week_start, health_score, health_flag, score_adoption, score_support, score_engagement,
                score_commercial, score_onboarding FROM health_weekly WHERE customer_id=? ORDER BY week_start""", (cid,))
    usage = q("""SELECT week_start, seats_licensed, active_users, seat_utilisation, queries, ai_assistant_queries, dashboards_created
                 FROM weekly_usage WHERE customer_id=? ORDER BY week_start""", (cid,))
    contacts = q("SELECT name, role, is_champion, is_exec_sponsor, joined_date, left_date, is_active FROM contacts WHERE customer_id=?", (cid,))
    tickets = q("""SELECT ticket_id, created_at, category, subject, status, reopen_count, escalated, first_response_hours
                   FROM tickets WHERE customer_id=? ORDER BY created_at DESC LIMIT 10""", (cid,))
    emails = q1("""SELECT COUNT(*) sent, SUM(opened) opened, SUM(bounced) bounced, SUM(replied) replied
                   FROM email_events WHERE customer_id=?""", (cid,))
    miles = q("SELECT milestone, milestone_date, days_from_signup FROM onboarding_milestones WHERE customer_id=? ORDER BY milestone_date", (cid,))
    events = q("SELECT event_type, event_date, arr_delta, reason FROM contract_events WHERE customer_id=? ORDER BY event_date", (cid,))
    plays = q("SELECT play_id, triggered_on, experiment_group, variant, outcome FROM play_runs WHERE customer_id=? ORDER BY triggered_on DESC", (cid,))
    docs = q("SELECT doc_type, doc_date, title FROM documents WHERE customer_id=? ORDER BY doc_date DESC LIMIT 8", (cid,))
    timeline = sorted(
        [{"date": t["created_at"][:10], "type": "ticket", "text": f"{t['category']}: {t['subject']}" + (" (escalated)" if t["escalated"] else "")} for t in tickets[:5]]
        + [{"date": p["triggered_on"], "type": "play", "text": f"Play: {p['play_id']} ({p['experiment_group']})"} for p in plays[:5]]
        + [{"date": m["milestone_date"], "type": "milestone", "text": m["milestone"]} for m in miles]
        + [{"date": c["left_date"], "type": "contact", "text": f"{c['name']} ({c['role']}) left"} for c in contacts if c["left_date"]],
        key=lambda x: x["date"], reverse=True)[:12]
    return {"customer": cust, "health": cur, "history": hist, "usage": usage, "contacts": contacts, "tickets": tickets,
            "email_summary": emails, "milestones": miles, "contract_events": events, "plays": plays, "documents": docs,
            "timeline": timeline, "recommendation": recommend(cur) if cur else None}


def cohorts():
    return {"size": q("SELECT * FROM cohort_size"), "tier": q("SELECT * FROM cohort_tier"),
            "signup_quarter": q("SELECT * FROM cohort_signup_quarter"), "retention_matrix": q("SELECT * FROM cohort_retention_matrix")}


def rfm(segment=None):
    rows = q("""SELECT r.customer_id, h.company_name, h.size_band, h.tier, r.recency_days, ROUND(r.frequency,2) frequency,
                r.monetary_arr, r.R, r.F, r.M, r.rfm_segment, h.health_score, h.health_flag
                FROM rfm_customers r JOIN health_current h USING(customer_id)
                WHERE (? IS NULL OR r.rfm_segment=?) ORDER BY r.monetary_arr DESC LIMIT 200""", (segment, segment))
    return {"summary": q("SELECT * FROM rfm_summary"), "customers": rows}


def plays():
    cat = q("SELECT * FROM play_catalog")
    stats = q("""SELECT play_id, experiment_group, variant, COUNT(*) runs,
                 SUM(outcome!='pending') measured, ROUND(AVG(delta_4w),3) mean_delta_4w,
                 ROUND(1.0*SUM(outcome='improved')/NULLIF(SUM(outcome!='pending'),0),3) improved_rate
                 FROM play_runs GROUP BY play_id, experiment_group, variant ORDER BY play_id, experiment_group, variant""")
    return {"catalog": cat, "stats": stats}


def alerts():
    """Daily digest: who changed state or needs attention, with a suggested next step."""
    rows = q("""SELECT h.*, p.health_score prev_score, p.health_flag prev_flag FROM health_current h
                LEFT JOIN health_weekly p ON p.customer_id=h.customer_id AND p.week_start=date(?, '-7 day')""", (LATEST_WEEK,))
    out = []
    for r in rows:
        tags = (r["driver_tags"] or "").split(";")
        rec = recommend(r)
        sev = None
        if r["health_flag"] == "At risk" and r["prev_flag"] != "At risk":
            sev, what = "High", f"Dropped into At risk this week ({r['prev_score']} to {r['health_score']})"
        elif r["health_flag"] == "At risk" and r["days_to_renewal"] is not None and r["days_to_renewal"] <= 120:
            sev, what = "High", f"At risk with renewal in {r['days_to_renewal']} days"
        elif "champion_left" in tags and (r["days_to_renewal"] or 999) <= 150:
            sev, what = "High", "Champion left and renewal is near"
        elif r["health_flag"] == "Watch" and r["prev_flag"] == "Healthy":
            sev, what = "Medium", f"Slipped to Watch ({r['prev_score']} to {r['health_score']})"
        elif "stalled_onboarding" in tags and r["lifecycle_stage"] == "Onboarding":
            sev, what = "Medium", "Onboarding stalled"
        elif (r["seat_utilisation"] or 0) > 0.85 and r["health_flag"] == "Healthy":
            sev, what = "Opportunity", f"Seat use at {round(r['seat_utilisation'] * 100)}%"
        if sev:
            out.append({"severity": sev, "customer_id": r["customer_id"], "company_name": r["company_name"], "tier": r["tier"],
                        "arr_current": r["arr_current"], "health_score": r["health_score"], "what_changed": what,
                        "driver_tags": r["driver_tags"], "next_step": rec["action"], "why": rec["why"]})
    order = {"High": 0, "Medium": 1, "Opportunity": 2}
    out.sort(key=lambda x: (order[x["severity"]], -(x["arr_current"] or 0)))
    return {"date": SNAPSHOT, "count": len(out), "alerts": out}


def program_impact():
    ab = q("""SELECT variant, COUNT(*) n, ROUND(AVG(delta_4w),3) mean_delta, ROUND(1.0*SUM(outcome='improved')/COUNT(*),3) improved_rate
              FROM play_runs WHERE play_id='adoption_nudge' AND outcome!='pending' GROUP BY variant""")
    onb = q("""SELECT experiment_group, COUNT(*) n, ROUND(AVG(delta_4w),3) mean_delta FROM play_runs
               WHERE play_id='onboarding_stall' AND outcome!='pending' GROUP BY experiment_group""")
    ttfv = q("""SELECT c.tier, COUNT(*) customers, ROUND(AVG(m.days_from_signup),1) avg_days,
                ROUND(100.0*SUM(m.days_from_signup<=30)/COUNT(*),1) pct_within_30d
                FROM onboarding_milestones m JOIN customers c USING(customer_id)
                WHERE m.milestone='shared_by_second_user' GROUP BY c.tier""")
    return {"adoption_nudge_ab": ab, "onboarding_stall_vs_control": onb, "time_to_first_value_by_tier": ttfv,
            "note": "Compare against control: new accounts ramp up on their own, so raw improvement overstates a play's effect."}
