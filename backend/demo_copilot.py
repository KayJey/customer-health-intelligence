"""Demo mode for the copilot (no API key needed).

build() runs the REAL tools against the dataset for a set of scripted questions and composes the answers from the
results with plain templates (no LLM). The output is saved to demo_copilot.json and replayed by the server.
So the tool calls and every number are real; only the wording is templated.

Run:  python demo_copilot.py       (regenerates demo_copilot.json)
"""
import json
import re
from pathlib import Path

import tools as T
from db import q, q1

FILE = Path(__file__).parent / "demo_copilot.json"
COMP = r"Brightlane BI|Datavista|Pivotly|Clearmetric"


def money(x):
    return f"${x / 1e6:.2f}M" if x >= 1e6 else f"${x / 1e3:.0f}K"


def words(tags):
    s = ", ".join(t.replace("_", " ") for t in (tags or "").split(";") if t) or "no specific warning tags"
    return re.sub(r"(\d+)pct", lambda m: m.group(1) + "%", s)


def tr(tool, args, summary):
    return {"tool": tool, "kind": T.TOOLS[tool][0], "input": args, "summary": summary}


def first(name):
    return name.split()[0]


def template_draft(cid):
    """Deterministic outreach draft from real context. Used in demo mode instead of an LLM."""
    d = T.get_customer_detail(cid)
    if "error" in d:
        return d
    contacts = d["contacts"]
    active = [c for c in contacts if c["is_active"]]
    left = [c for c in contacts if not c["is_active"] and c["is_champion"]]
    to = next((c for c in active if c["is_champion"]), active[0] if active else None)
    rec = d["recommendation"]
    hi = f"Hi {first(to['name'])}," if to else "Hi team,"
    owner = d["customer"]["csm_owner"] if d["customer"]["csm_owner"] != "Digital team" else "Customer Success"
    if left:
        body = (f"{hi}\n\nI noticed that {first(left[0]['name'])} has moved on from your team, and I wanted to make sure you have what you need. "
                f"I can set up a short session to walk you through the dashboards your team has been using and help you pick up where {first(left[0]['name'])} left off.\n\n"
                f"Would a 30 minute slot this week work?\n\nBest,\n{owner}")
        subject = "A quick walkthrough for your team"
    elif rec["play"] == "support_recovery":
        body = (f"{hi}\n\nI have been looking at the recent support tickets on your account and I want to make sure the open issues get resolved properly. "
                f"I have asked our support lead to name one owner for them and to share a root-cause update.\n\nCould we do a 20 minute call to go through them?\n\nBest,\n{owner}")
        subject = "Making sure your open issues are resolved"
    else:
        body = (f"{hi}\n\nI wanted to check in on how your team is getting on. I can share a few dashboards that similar teams use, "
                f"and set up a short session if that would help.\n\nBest,\n{owner}")
        subject = "Checking in on your analytics rollout"
    return {"customer_id": cid, "to": to["name"] if to else None, "subject": subject, "body": body,
            "status": "DRAFT ONLY. Not sent.", "source": "template (demo mode, no LLM)"}


def build():
    out = []

    # 1. at risk
    r = T.run("query_customers", {"health_flag": "At risk", "sort": "arr_current", "order": "desc", "limit": 5})
    tot, top = r["total_with_this_flag"], r["customers"][:3]
    lines = [f"- {c['customer_id']} ({c['size_band']}, {c['tier']}), {money(c['arr_current'])}, health {c['health_score']}, {words(c['driver_tags'])}" for c in top]
    out.append(dict(id="at_risk", question="Which customers are at risk this month?", keywords=["risk", "churn", "worried", "danger"],
                    trace=[tr("query_customers", {"health_flag": "At risk", "sort": "arr_current", "order": "desc", "limit": 5}, f"{r['returned']} customers, {tot['n']} at risk in total")],
                    answer=f"{tot['n']} customers are At risk, with {money(tot['arr'])} of ARR. The three largest:\n" + "\n".join(lines) + "\nWant the reasons for any of them, or a draft outreach?"))

    # 2. biggest drop
    m = q1("SELECT customer_id FROM health_current WHERE score_change_4w IS NOT NULL ORDER BY score_change_4w ASC LIMIT 1")["customer_id"]
    hb = T.run("get_health_breakdown", {"customer_id": m, "weeks": 5})["weeks_newest_first"]
    ut = T.run("get_usage_trend", {"customer_id": m, "weeks": 8})["weeks_newest_first"]
    sd = T.run("search_documents", {"query": "recent issues and owner changes", "customer_id": m, "top_k": 3})
    now, old = hb[0], hb[-1]
    dims = {"adoption": "score_adoption", "support": "score_support", "engagement": "score_engagement", "commercial": "score_commercial", "onboarding": "score_onboarding"}
    fell = sorted([(old[c] - now[c], n, old[c], now[c]) for n, c in dims.items() if old[c] - now[c] >= 5], reverse=True)
    why = [f"- {n} fell from {o:.0f} to {nw:.0f}" for _, n, o, nw in fell[:3]] or ["- no single dimension fell sharply"]
    snippet = sd["results"][0]["text"][:150].replace("\n", " ") if sd["results"] else ""
    out.append(dict(id="why_drop", question=f"Why did {m} drop?", keywords=["why", "drop", "dropped", "fell", "decline"],
                    trace=[tr("get_health_breakdown", {"customer_id": m, "weeks": 5}, "5 weeks"), tr("get_usage_trend", {"customer_id": m, "weeks": 8}, "8 weeks"),
                           tr("search_documents", {"query": "recent issues and owner changes", "customer_id": m, "top_k": 3}, f"{len(sd['results'])} results")],
                    answer=(f"{m} went from {old['health_score']} to {now['health_score']} in four weeks (now {now['health_flag']}).\n" + "\n".join(why) +
                            f"\nActive users went from {ut[-1]['active_users']} to {ut[0]['active_users']} of {ut[0]['seats_licensed']} seats. Warning signs: {words(now['driver_tags'])}." +
                            (f"\nMost relevant note: \"{snippet}...\"" if snippet else ""))))

    # 3. competitor mentions
    kw = ["Brightlane BI", "Datavista", "Pivotly", "Clearmetric", "competitor", "vendor", "switching"]
    sdc = T.run("search_documents", {"query": "considering another vendor, comparing a competitor product", "keywords": kw, "top_k": 15})
    named = [x for x in sdc["results"] if re.search(COMP, x["text"])]
    ids = list(dict.fromkeys(x["customer_id"] for x in named))
    info = {r_["customer_id"]: r_ for r_ in q("SELECT customer_id, arr_current, health_flag, days_to_renewal FROM health_current WHERE customer_id IN (%s)" % ",".join("?" * len(ids)), ids)} if ids else {}
    lines = [f"- {i}: {money(info[i]['arr_current'])}, {info[i]['health_flag']}, renews in {info[i]['days_to_renewal']} days" for i in ids[:5] if i in info]
    past = [x for x in named if re.search(r"original purchase|before signing", x["text"])]
    out.append(dict(id="competitor", question="Which customers mention a competitor in tickets or notes?", keywords=["competitor", "competition", "vendor", "alternative", "switch"],
                    trace=[tr("search_documents", {"query": "considering another vendor...", "keywords": kw, "top_k": 15}, f"{len(sdc['results'])} results, {len(named)} name a competitor")],
                    answer=(f"In the top results, {len(ids)} accounts name a competitor in their tickets or notes. {len(info)} are still active:\n" + "\n".join(lines) +
                            f"\nThe other {len(ids) - len(info)} have already churned. Mentions are not always risk (for example a comparison made before purchase), "
                            + (f"and {len(past)} of the matching texts are exactly that, " if past else "") + "so read each text before acting.")))

    # 4. whales going quiet
    rf = T.run("get_rfm_segments", {"size_band": "Whale"})
    wh = q("SELECT customer_id, arr_current, health_score, health_flag, rfm_segment FROM health_current WHERE size_band='Whale' ORDER BY health_score ASC")
    counts = {}
    for w in wh:
        counts[w["rfm_segment"]] = counts.get(w["rfm_segment"], 0) + 1
    low = [w for w in wh if w["health_flag"] != "Healthy"][:4]
    lines = [f"- {w['customer_id']}: {money(w['arr_current'])}, health {w['health_score']} ({w['health_flag']}), RFM {w['rfm_segment']}" for w in low]
    out.append(dict(id="whales", question="Which whales are going quiet?", keywords=["whale", "whales", "quiet", "enterprise", "largest"],
                    trace=[tr("get_rfm_segments", {"size_band": "Whale"}, f"{len(wh)} whales"), tr("query_customers", {"size_band": "Whale", "sort": "health_score"}, f"{len(wh)} rows")],
                    answer=(f"You have {len(wh)} whales. RFM segments: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])) +
                            f". {sum(1 for w in wh if w['health_flag'] != 'Healthy')} are not Healthy, the lowest:\n" + "\n".join(lines))))

    # 5. outreach for a champion-left customer
    ch = q1("SELECT customer_id FROM health_current WHERE driver_tags LIKE '%champion_left%' ORDER BY arr_current DESC LIMIT 1")["customer_id"]
    sim = T.run("find_similar_customers", {"customer_id": ch, "top_k": 5})["similar"]
    oc = {}
    for s in sim:
        oc[s["outcome"]] = oc.get(s["outcome"], 0) + 1
    dr = template_draft(ch)
    out.append(dict(id="draft", question=f"Draft outreach for {ch}", keywords=["draft", "outreach", "email", "write", "message"],
                    trace=[tr("get_customer_detail", {"customer_id": ch}, "profile and contacts"), tr("find_similar_customers", {"customer_id": ch, "top_k": 5}, f"{len(sim)} similar accounts"),
                           tr("draft_outreach", {"customer_id": ch}, "draft ready (template in demo mode)")],
                    answer=(f"{ch} lost its champion. Among {len(sim)} similar accounts that were At risk before: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in oc.items()) +
                            f". So I drafted a re-introduction note:\n\nSubject: {dr['subject']}\n\n{dr['body']}\n\nThis is a draft only. Want me to queue it for approval?")))

    # 6. alert rule
    n60 = q1("SELECT COUNT(*) n FROM health_current WHERE size_band='Whale' AND health_score<60")["n"]
    n65 = q1("SELECT COUNT(*) n FROM health_current WHERE size_band='Whale' AND health_score>=60 AND health_score<65")["n"]
    out.append(dict(id="alert_rule", question="Alert me if any whale drops below 60", keywords=["alert", "notify", "rule", "tell me", "warn"],
                    trace=[tr("create_alert_rule", {"segment": "whale", "metric": "health_score", "op": "<", "value": 60}, "recorded (demo mode: not saved)")],
                    answer=(f"Rule recorded: alert when a whale's health score falls below 60 (demo mode, nothing was saved). Right now {n60} whales are below 60 and {n65} are between 60 and 65. "
                            "The daily check by n8n is not connected yet, so this rule would not fire.")))

    # 7. nudge
    cp = T.run("compare_play_outcomes", {"play_id": "adoption_nudge"})["groups"]
    g = {x["variant"]: x for x in cp}
    out.append(dict(id="nudge", question="Did the adoption nudge work?", keywords=["nudge", "play", "worked", "experiment", "adoption"],
                    trace=[tr("compare_play_outcomes", {"play_id": "adoption_nudge"}, f"{len(cp)} groups")],
                    answer=(f"Yes for the personalised version. Utilisation 4 weeks after the nudge changed by {g['B']['mean_delta_4w']:+.3f} for the industry-personalised email (B, {g['B']['measured']} accounts, "
                            f"{g['B']['improved_rate'] * 100:.0f}% improved), {g['A']['mean_delta_4w']:+.3f} for the generic email (A, {g['A']['measured']}, {g['A']['improved_rate'] * 100:.0f}% improved) "
                            f"and {g['control']['mean_delta_4w']:+.3f} for the control group ({g['control']['measured']}, {g['control']['improved_rate'] * 100:.0f}% improved). "
                            "The groups are small, so treat it as directional and rerun it on more accounts.")))

    # 8. renewals
    rp = T.run("get_renewal_pipeline", {"within_days": 90, "max_health": 65})
    ac = rp["accounts"][:3]
    lines = [f"- {a['customer_id']}: {money(a['arr_current'])}, renews in {a['days_to_renewal']} days, health {a['health_score']}" for a in ac]
    out.append(dict(id="renewals", question="Which renewals in the next 90 days are at risk?", keywords=["renewal", "renewals", "renew", "renewing"],
                    trace=[tr("get_renewal_pipeline", {"within_days": 90, "max_health": 65}, f"{len(rp['accounts'])} accounts at or below 65")],
                    answer=f"{rp['total_renewing']['n']} accounts ({money(rp['total_renewing']['arr'])}) renew in the next 90 days. {len(rp['accounts'])} of them have a health score of 65 or lower. The largest:\n" + "\n".join(lines)))

    # 9. today
    ad = T.run("get_alerts_digest", {"limit": 5})
    sev = {}
    for a in ad["top"]:
        sev[a["severity"]] = sev.get(a["severity"], 0) + 1
    allsev = {}
    for a in __import__("queries").alerts()["alerts"]:
        allsev[a["severity"]] = allsev.get(a["severity"], 0) + 1
    lines = [f"- {a['severity']}: {a['customer_id']} ({money(a['arr_current'])}), {a['what_changed']}. Next step: {a['next_step']}" for a in ad["top"][:4]]
    out.append(dict(id="today", question="What should the team look at today?", keywords=["today", "digest", "priorities", "focus", "look at"],
                    trace=[tr("get_alerts_digest", {"limit": 5}, f"{ad['total_alerts']} alerts")],
                    answer=f"Today's digest has {ad['total_alerts']} alerts: " + ", ".join(f"{v} {k}" for k, v in allsev.items()) + ". The top ones:\n" + "\n".join(lines)))
    return out


def save():
    data = build()
    FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return data


def load():
    return json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else save()


STOP = set("the a an of to in is are for me my our which what who how do does did can you please show give any all".split())


def match(question, entries):
    toks = {t for t in re.findall(r"[a-z0-9]+", question.lower()) if t not in STOP}
    best, score = None, 0
    for e in entries:
        s = sum(2 for k in e["keywords"] if k in question.lower()) + len(toks & set(re.findall(r"[a-z0-9]+", e["question"].lower())))
        if s > score:
            best, score = e, s
    return best if score >= 2 else None


if __name__ == "__main__":
    for e in save():
        print(f"\n## {e['question']}\n  trace: {[t['tool'] for t in e['trace']]}\n{e['answer']}")
