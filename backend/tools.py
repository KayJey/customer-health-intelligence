"""The copilot's toolbox. Each tool has a kind (sql, vector, compute, llm, action), a JSON schema for the model,
and a Python function that returns plain JSON-able data. The model picks tools; we execute them; results go back to the model.

Write tools (create_alert_rule, send_for_approval, handoff_to_csm) only record to app.db. Nothing is sent externally:
the n8n webhook is a later step, and every outreach is a draft that a human approves.
"""
import re
import sqlite3
from functools import lru_cache

import pandas as pd

import llm
import queries as Q
from db import LATEST_WEEK, ROOT, app_db, q, q1

_col = None


def _collection():
    global _col
    if _col is None:
        from build_vector_index import get_collection
        _col = get_collection()
    return _col


def _cap(rows, n=25):
    return rows[:n]


# ------------------------------------------------------------------ SQL tools
def query_customers(tier=None, lifecycle_stage=None, industry=None, size_band=None, health_flag=None,
                    renewal_within_days=None, search=None, sort="health_score", order="asc", limit=15):
    r = Q.customers(tier, lifecycle_stage, industry, size_band, health_flag, renewal_within_days, search, sort, order, min(int(limit), 25))
    cols = ["customer_id", "size_band", "tier", "lifecycle_stage", "industry", "arr_current", "health_score", "health_flag",
            "score_change_4w", "days_to_renewal", "top_driver", "driver_tags", "rfm_segment"]
    total = q1("SELECT COUNT(*) n, ROUND(SUM(arr_current)) arr FROM health_current WHERE health_flag=?", (health_flag,)) if health_flag else None
    out = {"returned": r["count"], "customers": [{k: c[k] for k in cols} for c in r["customers"]]}
    if total:
        out["total_with_this_flag"] = total
    return out


def get_customer_detail(customer_id):
    d = Q.customer_detail(customer_id)
    if not d:
        return {"error": f"No customer {customer_id}"}
    h = d["health"] or {}
    return {"customer": {k: d["customer"][k] for k in ["customer_id", "industry", "size_band", "tier", "csm_owner", "signup_date",
                                                       "arr_current", "seats_current", "status", "churn_date", "next_renewal_date", "lifecycle_stage"]},
            "health": {k: h.get(k) for k in ["health_score", "health_flag", "score_change_4w", "weeks_in_flag", "score_adoption", "score_support",
                                             "score_engagement", "score_commercial", "score_onboarding", "top_driver", "driver_tags", "rfm_segment", "seat_utilisation"]} if h else None,
            "contacts": d["contacts"], "recent_tickets": d["tickets"][:5], "email_summary": d["email_summary"],
            "milestones": d["milestones"], "contract_events": d["contract_events"], "plays": d["plays"][:6],
            "recent_documents": d["documents"][:5], "recommendation": d["recommendation"]}


def get_health_breakdown(customer_id, weeks=8):
    rows = q("""SELECT week_start, health_score, health_flag, score_adoption, score_support, score_engagement, score_commercial,
                score_onboarding, top_driver, driver_tags FROM health_weekly WHERE customer_id=? ORDER BY week_start DESC LIMIT ?""",
             (customer_id, int(weeks)))
    return {"customer_id": customer_id, "weeks_newest_first": rows} if rows else {"error": f"No health data for {customer_id}"}


def get_usage_trend(customer_id, weeks=12):
    rows = q("""SELECT week_start, seats_licensed, active_users, seat_utilisation, queries, ai_assistant_queries, dashboards_created,
                features_used FROM weekly_usage WHERE customer_id=? ORDER BY week_start DESC LIMIT ?""", (customer_id, int(weeks)))
    return {"customer_id": customer_id, "weeks_newest_first": rows}


def get_ticket_stats(customer_id=None, days=60, only_problem_accounts=False):
    where = "t.created_at >= date(?, ?)"
    p = [LATEST_WEEK, f"-{int(days)} day"]
    if customer_id:
        where += " AND t.customer_id=?"
        p.append(customer_id)
    rows = q(f"""SELECT t.customer_id, COUNT(*) tickets, SUM(t.escalated) escalated, SUM(t.reopen_count>0) reopened,
                 ROUND(AVG(t.first_response_hours),1) avg_first_response_h, SUM(t.status='open') still_open
                 FROM tickets t WHERE {where} GROUP BY t.customer_id
                 {'HAVING escalated>0 OR reopened>0' if only_problem_accounts else ''}
                 ORDER BY escalated DESC, reopened DESC LIMIT 20""", p)
    return {"window_days": int(days), "accounts": rows}


def get_renewal_pipeline(within_days=120, max_health=None):
    rows = q("""SELECT customer_id, tier, size_band, arr_current, next_renewal_date, days_to_renewal, health_score, health_flag, driver_tags
                FROM health_current WHERE days_to_renewal<=? AND (? IS NULL OR health_score<=?) ORDER BY arr_current DESC LIMIT 25""",
             (int(within_days), max_health, max_health))
    tot = q1("SELECT COUNT(*) n, ROUND(SUM(arr_current)) arr FROM health_current WHERE days_to_renewal<=?", (int(within_days),))
    return {"within_days": int(within_days), "total_renewing": tot, "accounts": rows}


def get_alerts_digest(limit=15):
    a = Q.alerts()
    return {"date": a["date"], "total_alerts": a["count"], "top": _cap(a["alerts"], int(limit))}


# ------------------------------------------------------------------ vector / hybrid search
def search_documents(query, keywords=None, customer_id=None, doc_type=None, top_k=8):
    """Hybrid search over tickets, call notes, QBR notes and NPS comments:
    vector similarity (meaning) plus keyword match (exact terms), merged by reciprocal rank fusion."""
    top_k = min(int(top_k), 15)
    clauses = []
    if customer_id:
        clauses.append({"customer_id": customer_id})
    if doc_type:
        clauses.append({"doc_type": doc_type})
    where = None if not clauses else clauses[0] if len(clauses) == 1 else {"$and": clauses}
    kw = dict(where=where) if where else {}
    vec = _collection().query(query_texts=[query], n_results=30, **kw)
    ranks, info = {}, {}
    for r, (i, m, d) in enumerate(zip(vec["ids"][0], vec["metadatas"][0], vec["documents"][0])):
        ranks.setdefault(i, {})["vector"] = r
        info[i] = {"doc_id": i, "customer_id": m["customer_id"], "doc_type": m["doc_type"], "date": m["doc_date"], "text": d.split("\n", 1)[-1]}
    if keywords:
        terms = [re.sub(r'[^\w\s-]', ' ', k).strip() for k in keywords if k.strip()]
        fts_q = " OR ".join(f'"{t}"' for t in terms if t)
        if fts_q:
            sql = "SELECT doc_id, customer_id, doc_type, doc_date, text FROM docs_fts WHERE docs_fts MATCH ?"
            params = [fts_q]
            if customer_id:
                sql += " AND customer_id=?"
                params.append(customer_id)
            if doc_type:
                sql += " AND doc_type=?"
                params.append(doc_type)
            con = sqlite3.connect(ROOT / "data" / "search.db")
            for r, row in enumerate(con.execute(sql + " ORDER BY rank LIMIT 30", params)):
                ranks.setdefault(row[0], {})["keyword"] = r
                info.setdefault(row[0], {"doc_id": row[0], "customer_id": row[1], "doc_type": row[2], "date": row[3], "text": row[4]})
            con.close()
    scored = sorted(ranks, key=lambda i: -sum(1 / (60 + r) for r in ranks[i].values()))[:top_k]
    return {"query": query, "keywords": keywords or [], "results": [
        {**{k: v for k, v in info[i].items() if k != "text"}, "matched_by": sorted(ranks[i]), "text": info[i]["text"][:420]} for i in scored],
        "note": "Mentions can be noise (for example a past purchase comparison). Read the text before concluding a customer is at risk."}


@lru_cache(maxsize=1)
def _history_profile():
    hw = pd.DataFrame(q("SELECT customer_id, health_score, health_flag, driver_tags FROM health_weekly"))
    cu = pd.DataFrame(q("SELECT customer_id, size_band, tier, industry, status FROM customers")).set_index("customer_id")
    cur = pd.DataFrame(q("SELECT customer_id, health_flag FROM health_current")).set_index("customer_id").health_flag
    rows = {}
    for cid, g in hw.groupby("customer_id"):
        tags = set(t.split("_down")[0] if t.startswith("usage_down") else t for s in g.driver_tags.dropna() for t in s.split(";") if t)
        ever_risk = bool((g.health_score < 60).any())
        status = cu.loc[cid, "status"]
        outcome = "churned" if status == "churned" else ("recovered" if ever_risk and cur.get(cid) != "At risk" else
                                                          "still_at_risk" if cur.get(cid) == "At risk" else "never_at_risk")
        rows[cid] = dict(tags=tags, ever_risk=ever_risk, outcome=outcome, **cu.loc[cid, ["size_band", "tier", "industry"]].to_dict())
    return rows


def find_similar_customers(customer_id, top_k=5):
    """Customers with a similar profile and similar warning signs, and how they turned out. Observable outcomes only."""
    prof = _history_profile()
    if customer_id not in prof:
        return {"error": f"No customer {customer_id}"}
    me = prof[customer_id]
    res = []
    for cid, o in prof.items():
        if cid == customer_id or not o["ever_risk"]:
            continue
        jac = len(me["tags"] & o["tags"]) / max(1, len(me["tags"] | o["tags"]))
        s = 0.5 * jac + 0.2 * (me["size_band"] == o["size_band"]) + 0.15 * (me["tier"] == o["tier"]) + 0.15 * (me["industry"] == o["industry"])
        res.append((s, cid, o))
    res.sort(key=lambda x: -x[0])
    return {"customer_id": customer_id, "its_warning_signs": sorted(me["tags"]),
            "similar": [{"customer_id": c, "similarity": round(s, 2), "shared_signs": sorted(me["tags"] & o["tags"]), "outcome": o["outcome"],
                         "size_band": o["size_band"], "tier": o["tier"]} for s, c, o in res[:min(int(top_k), 10)]],
            "note": "Only customers that were At risk at some point are compared. 'recovered' = was At risk, now Watch or Healthy."}


# ------------------------------------------------------------------ compute tools
def get_cohort_retention():
    return Q.cohorts()


def get_rfm_segments(segment=None, size_band=None):
    r = Q.rfm(segment)
    if size_band:
        r["customers"] = [c for c in r["customers"] if c["size_band"] == size_band]
    r["customers"] = r["customers"][:20]
    return r


def compare_play_outcomes(play_id):
    p = Q.plays()
    return {"play_id": play_id, "groups": [s for s in p["stats"] if s["play_id"] == play_id],
            "caveat": "Compare treated to control. Raw 4-week improvement also includes natural ramp-up. Small groups, so treat as directional."}


def recommend_next_action(customer_id):
    c = q1("SELECT * FROM health_current WHERE customer_id=?", (customer_id,))
    return Q.recommend(c) | {"customer_id": customer_id, "health_score": c["health_score"], "driver_tags": c["driver_tags"]} if c else {"error": f"No active customer {customer_id}"}


# ------------------------------------------------------------------ LLM tool
def draft_outreach(customer_id, play=None):
    d = get_customer_detail(customer_id)
    if "error" in d:
        return d
    rec = d["recommendation"]
    notes = search_documents("recent account situation and next steps", customer_id=customer_id, top_k=3)["results"]
    ctx = (f"Customer {customer_id}: {d['customer']['size_band']} {d['customer']['industry']} account, tier {d['customer']['tier']}. "
           f"Health {d['health']['health_score']} ({d['health']['health_flag']}), warning signs: {d['health']['driver_tags'] or 'none'}. "
           f"Play: {play or rec['play'] or 'check-in'}. Recommended action: {rec['action']} ({rec['why']}). "
           f"Contacts: {[(c['name'], c['role'], 'active' if c['is_active'] else 'left') for c in d['contacts']]}. "
           f"Recent notes: {[n['text'][:200] for n in notes]}")
    text = llm.complete("You write short, warm, specific customer success emails (under 110 words). Plain text, a subject line first. "
                        "Do not invent facts, discounts or dates beyond the context. Address an active contact, never one who has left.", ctx)
    return {"customer_id": customer_id, "draft": text, "status": "DRAFT ONLY. Not sent. Use send_for_approval to queue it."}


# ------------------------------------------------------------------ action tools (record only)
def create_alert_rule(segment, metric, op, value, channel="digest"):
    if op not in ("<", "<=", ">", ">=") or metric not in ("health_score", "seat_utilisation", "score_change_4w"):
        return {"error": "metric must be health_score, seat_utilisation or score_change_4w; op one of < <= > >="}
    con = app_db()
    cur = con.execute("INSERT INTO alert_rules (segment, metric, op, value, channel) VALUES (?,?,?,?,?)", (segment, metric, op, float(value), channel))
    con.commit()
    rid = cur.lastrowid
    col = {"whale": "size_band='Whale'", "sme": "size_band='SME'", "mid": "size_band='Mid'", "all": "1=1"}.get(str(segment).lower())
    now = q1(f"SELECT COUNT(*) n FROM health_current WHERE {col} AND {metric} {op} ?", (float(value),))["n"] if col else None
    return {"rule_id": rid, "recorded": True, "currently_matching": now,
            "note": "Rule saved in app.db. The scheduled n8n workflow that evaluates it is not connected yet."}


def send_for_approval(customer_id, subject, body):
    con = app_db()
    cur = con.execute("INSERT INTO approvals (customer_id, kind, subject, body) VALUES (?,?,?,?)", (customer_id, "outreach", subject, body))
    con.commit()
    return {"approval_id": cur.lastrowid, "status": "pending", "note": "Queued for human approval. Nothing has been sent."}


def handoff_to_csm(customer_id, reason):
    con = app_db()
    cur = con.execute("INSERT INTO approvals (customer_id, kind, subject, body) VALUES (?,?,?,?)", (customer_id, "handoff", "Move to CSM-led", reason))
    con.commit()
    return {"approval_id": cur.lastrowid, "status": "pending", "note": "Handoff request recorded for a human to confirm."}


# ------------------------------------------------------------------ registry
def _s(props, req=()):
    return {"type": "object", "properties": props, "required": list(req)}


_cid = {"customer_id": {"type": "string", "description": "e.g. C0142"}}
TOOLS = {
    "query_customers": ("sql", query_customers, "Filter and rank active customers by tier, lifecycle stage, industry, size band (SME, Mid, Whale), health flag (Healthy, Watch, At risk) or renewal window.",
                        _s({"tier": {"type": "string", "enum": ["Digital", "Pooled", "CSM-led"]}, "lifecycle_stage": {"type": "string", "enum": ["Onboarding", "Adoption", "Renewal", "Expansion"]},
                            "industry": {"type": "string"}, "size_band": {"type": "string", "enum": ["SME", "Mid", "Whale"]}, "health_flag": {"type": "string", "enum": ["Healthy", "Watch", "At risk"]},
                            "renewal_within_days": {"type": "integer"}, "search": {"type": "string"},
                            "sort": {"type": "string", "enum": ["health_score", "arr_current", "days_to_renewal", "score_change_4w"]}, "order": {"type": "string", "enum": ["asc", "desc"]}, "limit": {"type": "integer"}}),
                        "Which customers are at risk?"),
    "get_customer_detail": ("sql", get_customer_detail, "Full profile for one customer: health, dimension scores, contacts, tickets, milestones, plays, recent documents, recommendation.", _s(_cid, ["customer_id"]), "Give me everything on C0142"),
    "get_health_breakdown": ("sql", get_health_breakdown, "Weekly health scores by dimension with warning tags for one customer, newest first. Use to explain why a score changed.", _s({**_cid, "weeks": {"type": "integer"}}, ["customer_id"]), "Why did C0142 drop?"),
    "get_usage_trend": ("sql", get_usage_trend, "Weekly active users, seat utilisation and queries for one customer.", _s({**_cid, "weeks": {"type": "integer"}}, ["customer_id"]), "Is C0087 still using the product?"),
    "get_ticket_stats": ("sql", get_ticket_stats, "Support ticket counts, escalations, reopens and first response time per account over a window; optionally one customer or only problem accounts.",
                         _s({**_cid, "days": {"type": "integer"}, "only_problem_accounts": {"type": "boolean"}}), "Who has repeat reopened tickets?"),
    "get_renewal_pipeline": ("sql", get_renewal_pipeline, "Upcoming renewals with ARR and health, optionally only accounts at or below a health score.", _s({"within_days": {"type": "integer"}, "max_health": {"type": "number"}}), "Which renewals are at risk next quarter?"),
    "get_alerts_digest": ("sql", get_alerts_digest, "Today's prioritised alert digest: new At-risk accounts, renewal risks, champion loss, opportunities, with suggested next steps.", _s({"limit": {"type": "integer"}}), "What should the team look at today?"),
    "search_documents": ("vector", search_documents, "Hybrid semantic plus keyword search over ticket threads, CSM call notes, QBR notes and NPS comments. Pass a natural-language query and, for exact terms such as competitor names, keywords. Can filter by customer or doc_type (ticket_thread, call_note, qbr_note, nps_comment).",
                         _s({"query": {"type": "string"}, "keywords": {"type": "array", "items": {"type": "string"}}, **_cid, "doc_type": {"type": "string", "enum": ["ticket_thread", "call_note", "qbr_note", "nps_comment"]}, "top_k": {"type": "integer"}}, ["query"]),
                         "Which customers mention a competitor?"),
    "find_similar_customers": ("vector", find_similar_customers, "Customers with a similar profile and warning signs that were At risk before, and how they turned out (churned, recovered, still at risk).", _s({**_cid, "top_k": {"type": "integer"}}, ["customer_id"]), "Who looks like C0142 and what happened to them?"),
    "get_cohort_retention": ("compute", get_cohort_retention, "Cohort tables: size bands, coverage tiers and signup-quarter retention, including gross and net revenue retention.", _s({}), "Do SME or whales retain better?"),
    "get_rfm_segments": ("compute", get_rfm_segments, "Usage-based RFM segments (Champions, Loyal, Promising, Light users, Need attention, At risk, Cannot lose, Hibernating) with counts, ARR and top customers.", _s({"segment": {"type": "string"}, "size_band": {"type": "string", "enum": ["SME", "Mid", "Whale"]}}), "Which whales are going quiet?"),
    "compare_play_outcomes": ("compute", compare_play_outcomes, "Treated vs control outcomes for a lifecycle play (onboarding_stall, adoption_nudge, champion_loss, renewal_readiness, expansion_signal), including A/B variants.", _s({"play_id": {"type": "string"}}, ["play_id"]), "Did the adoption nudge work?"),
    "recommend_next_action": ("compute", recommend_next_action, "Rule-based next best action for one customer with the reason.", _s(_cid, ["customer_id"]), "What should I do about C0087?"),
    "draft_outreach": ("llm", draft_outreach, "Draft a short personalised outreach email for one customer using its context. DRAFT ONLY, never sent.", _s({**_cid, "play": {"type": "string"}}, ["customer_id"]), "Draft outreach for C0142"),
    "create_alert_rule": ("action", create_alert_rule, "Record an alert rule (segment all, whale, mid or sme; metric health_score, seat_utilisation or score_change_4w; operator and value). Records only; evaluation by n8n is not connected yet.",
                          _s({"segment": {"type": "string"}, "metric": {"type": "string"}, "op": {"type": "string"}, "value": {"type": "number"}, "channel": {"type": "string"}}, ["segment", "metric", "op", "value"]), "Alert me if any whale drops below 60"),
    "send_for_approval": ("action", send_for_approval, "Queue a drafted message for human approval. Nothing is sent.", _s({**_cid, "subject": {"type": "string"}, "body": {"type": "string"}}, ["customer_id", "subject", "body"]), "Queue that email for approval"),
    "handoff_to_csm": ("action", handoff_to_csm, "Record a request to move a customer from digital to CSM-led coverage, for a human to confirm.", _s({**_cid, "reason": {"type": "string"}}, ["customer_id", "reason"]), "Move C0142 to a CSM"),
}


def schemas():
    return [{"name": n, "description": f"[{k}] {d}", "input_schema": s} for n, (k, f, d, s, e) in TOOLS.items()]


def catalog():
    return [{"name": n, "kind": k, "description": d, "example": e} for n, (k, f, d, s, e) in TOOLS.items()]


def run(name, args):
    if name not in TOOLS:
        return {"error": f"Unknown tool {name}"}
    try:
        return TOOLS[name][1](**(args or {}))
    except Exception as e:  # return the error to the model so it can recover
        return {"error": f"{type(e).__name__}: {e}"}
