"""Generate the synthetic customer-health dataset.

Run:  python generate.py            (writes CSVs to ../data/csv)

Tables written:
  customers, contacts, weekly_usage, onboarding_milestones, tickets, email_events,
  nps_responses, invoices, contract_events, play_catalog, play_runs, documents
  ground_truth  (hidden story arcs, for validation only; do not load into dashboards or models)
"""
import os
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

import texts as T
from config import *

rng = np.random.default_rng(SEED)
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "csv")
WEEKS = [START + timedelta(weeks=i) for i in range(N_WEEKS)]


def D(n):
    return timedelta(days=int(n))


def W(n):
    return timedelta(weeks=int(n))


def pick(seq, p=None):
    return seq[int(rng.choice(len(seq), p=p))]


def widx(d):
    i = (d - START).days // 7
    return i if 0 <= i < N_WEEKS else None


def at(d, hour=None):
    h = int(rng.integers(8, 18)) if hour is None else hour
    return datetime(d.year, d.month, d.day, h, int(rng.integers(0, 60)))


def season(d):
    s = 1.0
    if date(2025, 12, 20) <= d <= date(2026, 1, 4):
        s *= 0.82
    if d.month == 8:
        s *= 0.95
    return s


def decay(arc, t):
    if arc == "champion_loss":
        return (0.40 + 0.60 * np.exp(-t / 1.5)) * np.exp(-t / 40)
    if arc == "quiet_fade":
        return max(0.12, np.exp(-t / 13))
    if arc == "competitor_eval":
        return max(0.35, np.exp(-t / 28))
    if arc == "support_friction":
        return max(0.30, np.exp(-t / 12))
    return 1.0


# ---------------------------------------------------------------- customers
def build_customers():
    bands = sum(([b] * n for b, n in BAND_COUNTS.items()), [])
    rng.shuffle(bands)
    arcs = rng.choice(list(ARC_W), size=N_CUSTOMERS, p=list(ARC_W.values()))
    out = []
    for i in range(N_CUSTOMERS):
        band = bands[i]
        lo, hi = BAND_ARR[band]
        arr0 = round(float(np.exp(rng.uniform(np.log(lo), np.log(hi)))) / 100) * 100
        signup = SIGNUP_MIN + D(int(rng.integers(0, (SIGNUP_MAX - SIGNUP_MIN).days)))
        arc = str(arcs[i])
        if (SNAPSHOT - signup).days < 100:
            arc = pick(["healthy_steady", "late_bloomer", "slow_onboarding_stall"], [0.8, 0.1, 0.1])
        tier = pick(["Digital", "Pooled", "CSM-led"], TIER_P[band])
        price = float(rng.uniform(*PRICE_PER_SEAT))
        out.append(dict(
            customer_id=f"C{i + 1:04d}", company_name=f"Customer {i + 1:04d}", band=band, tier=tier,
            industry=pick(INDUSTRIES), use_case=pick(USE_CASES), region=pick(REGIONS, REGION_P),
            csm=pick(CSM_NAMES) if tier != "Digital" else "Digital team", signup=signup, arr0=float(arr0),
            price=price, arc=arc, base_ratio=float(np.clip(rng.normal(BASE_RATIO_MEAN[band], 0.12), 0.22, 0.85)),
            eng=float(np.clip(rng.beta(3, 3) * 0.65 + 0.15, 0.1, 0.8)), resp=float(rng.uniform(0.5, 1.5)),
            comp=pick(T.COMPETITORS)))
    return out


def plan(c):
    arc, sig = c["arc"], c["signup"]
    anns = [sig + D(365 * k) for k in range(1, 4)]
    R = next((a for a in anns if a >= START + D(60)), anns[-1])
    c.update(onset=None, saved=False, churn_date=None, churn_reason=None, target_renewal=R,
             expand_date=None, contraction=False, anns=anns)
    if arc in CHURN_P:
        if arc == "slow_onboarding_stall":
            onset = sig + D(21)
        else:
            onset = min(max(R - W(rng.integers(10, 25)), sig + D(28)), SNAPSHOT - D(35))
        c["onset"] = onset
        if rng.random() < CHURN_P[arc]:
            if R <= SNAPSHOT:
                c["churn_date"], c["churn_reason"] = R, CHURN_REASON[arc]
        elif R <= SNAPSHOT or rng.random() < 0.4:
            c["saved"] = True
            c["contraction"] = bool(rng.random() < 0.3)
    elif arc == "false_alarm":
        lo, hi = max(START, sig + D(60)), SNAPSHOT - D(70)
        if lo < hi:
            c["onset"] = lo + D(rng.integers(0, (hi - lo).days))
        else:
            c["arc"] = "healthy_steady"
    elif arc == "healthy_expanding":
        lo, hi = sig + D(120), SNAPSHOT - D(21)
        if lo < hi:
            c["expand_date"] = lo + D(rng.integers(0, (hi - lo).days))
        else:
            c["arc"] = "healthy_steady"
    if c["arc"] == "healthy_steady" and R <= SNAPSHOT and rng.random() < SURPRISE_CHURN_P:
        c["churn_date"], c["churn_reason"] = R, CHURN_REASON["surprise"]
    # contract events (ARR over time)
    cand = []
    for a in anns:
        if a > SNAPSHOT:
            break
        if c["churn_date"] and a == c["churn_date"]:
            cand.append((a, "churn", -1.0))
            break
        if a == R and c["saved"] and c["contraction"]:
            cand.append((a, "contraction", -0.15))
        elif c["arc"] in ("healthy_steady", "healthy_expanding", "late_bloomer") and rng.random() < 0.45:
            cand.append((a, "renewal", float(rng.uniform(0.03, 0.10))))
        else:
            cand.append((a, "renewal", 0.0))
    if c["expand_date"]:
        cand.append((c["expand_date"], "expansion", float(rng.uniform(0.2, 0.4))))
    cand.sort(key=lambda x: x[0])
    ev, arr = [("new", sig, c["arr0"])], c["arr0"]
    for d, typ, pct in cand:
        delta = round(arr * pct, 2)
        ev.append((typ, d, delta))
        arr += delta
    c["events"], c["arr_now"] = ev, max(arr, 0.0)


def arr_at(c, d):
    return sum(x[2] for x in c["events"] if x[1] <= d)


def phase(c, d):
    if c["onset"] is None or d < c["onset"]:
        return "ok"
    t = (d - c["onset"]).days / 7
    if c["arc"] == "false_alarm":
        return "ok_dip" if t < 6 else "ok"
    if c["saved"] and t > 14:
        return "recovering"
    return "concern" if t < 8 else "critical"


# ---------------------------------------------------------------- contacts
def make_contacts(c, rows):
    n = {"SME": int(rng.integers(2, 4)), "Mid": int(rng.integers(3, 5)), "Whale": int(rng.integers(4, 7))}[c["band"]]
    roles = ["BI Lead", "Data Analyst"] + (["VP Operations"] if c["band"] != "SME" else []) + \
        [pick(["Business User", "IT Admin", "Finance Analyst"]) for _ in range(max(0, n - 2 - (c["band"] != "SME")))]
    cn = c["customer_id"].lower()
    contacts = []
    for j, role in enumerate(roles):
        nm = f"{pick(FIRST)} {pick(LAST)}"
        k = dict(contact_id=f"{c['customer_id']}-P{j + 1}", customer_id=c["customer_id"], name=nm,
                 email=f"{nm.lower().replace(' ', '.')}@{cn}.example", role=role, is_champion=j == 0,
                 is_exec_sponsor=role == "VP Operations", joined=c["signup"], left=None)
        if j == 0 and c["arc"] == "champion_loss":
            k["left"] = max(c["onset"] - D(rng.integers(3, 12)), c["signup"] + D(14))
        elif j > 0 and rng.random() < 0.06:
            k["left"] = START + D(rng.integers(30, 330))
            if k["left"] <= c["signup"]:
                k["left"] = None
        contacts.append(k)
    if c["arc"] == "champion_loss" and c["saved"]:
        left = contacts[0]["left"]
        nm = f"{pick(FIRST)} {pick(LAST)}"
        contacts.append(dict(contact_id=f"{c['customer_id']}-P{len(contacts) + 1}", customer_id=c["customer_id"],
                             name=nm, email=f"{nm.lower().replace(' ', '.')}@{cn}.example", role="BI Lead",
                             is_champion=True, is_exec_sponsor=False, joined=left + W(rng.integers(3, 7)), left=None))
    for k in contacts:
        rows.append(dict(contact_id=k["contact_id"], customer_id=k["customer_id"], name=k["name"], email=k["email"],
                         role=k["role"], is_champion=k["is_champion"], is_exec_sponsor=k["is_exec_sponsor"],
                         joined_date=k["joined"], left_date=k["left"], is_active=k["left"] is None))
    return contacts


def active_contacts(contacts, d):
    return [x for x in contacts if x["joined"] <= d and (x["left"] is None or x["left"] > d)]


# ---------------------------------------------------------------- milestones
def make_milestones(c, rows):
    arc, sig = c["arc"], c["signup"]
    mult = {"SME": 1.2, "Mid": 1.0, "Whale": 0.7}[c["band"]] * (2.5 if arc == "late_bloomer" else 1) * \
        (1.8 if arc == "slow_onboarding_stall" else 1)
    d = sig + D(rng.uniform(1, 10) * mult)
    m = {"data_connected": d}
    d = d + D(rng.uniform(1, 7) * mult)
    m["first_search"] = d
    stall = arc == "slow_onboarding_stall"
    if not stall or rng.random() < 0.4:
        d = d + D(rng.uniform(1, 10) * mult)
        m["first_dashboard_created"] = d
        if not stall or rng.random() < 0.4:
            m["shared_by_second_user"] = d + D(rng.uniform(2, 14) * mult)
    for k, v in m.items():
        if v <= SNAPSHOT and (c["churn_date"] is None or v < c["churn_date"]):
            rows.append(dict(customer_id=c["customer_id"], milestone=k, milestone_date=v,
                             days_from_signup=(v - sig).days))
    return m


# ---------------------------------------------------------------- usage + plays
def base_ratios(c, m):
    arc, sig, onset = c["arc"], c["signup"], c["onset"]
    tau = {"late_bloomer": 14, "slow_onboarding_stall": 6}.get(arc, 3.5)
    ratios, seats = [], []
    for w, d in enumerate(WEEKS):
        if d + D(6) < sig or (c["churn_date"] and d >= c["churn_date"]):
            ratios.append(None)
            seats.append(None)
            continue
        age = max((d - sig).days / 7, 0)
        asym = 0.35 if arc == "slow_onboarding_stall" else 1.0
        t = (d - onset).days / 7 if onset and d >= onset else None
        if arc == "slow_onboarding_stall" and c["saved"] and t and t > 12:
            asym = 0.35 + 0.65 * (1 - np.exp(-(t - 12) / 6))
        r = c["base_ratio"] * asym * (1 - np.exp(-age / tau))
        if arc == "healthy_expanding":
            r *= 1 + 0.55 * (1 - np.exp(-age / 18))
        r *= season(d)
        f = 1.0
        if t is not None and arc in DECAY_ARCS:
            f = decay(arc, t)
            if c["saved"] and t > 12:
                f = f + (1 - f) * (1 - np.exp(-(t - 12) / 6)) * 0.85
        if t is not None and arc == "false_alarm":
            f = 0.42 if t < 6 else 0.7 if t < 7 else 0.9 if t < 8 else 1.0
        if c["churn_date"] and (c["churn_date"] - d).days <= 21:
            f *= 0.55
        r = r * f * float(np.exp(rng.normal(0, 0.05)))
        ratios.append(float(np.clip(r, 0.01, 0.97)))
        seats.append(max(3, int(round(arr_at(c, d + D(6)) / c["price"]))))
    return ratios, seats


def lift(ratios, i, amt, k=5.0):
    for j in range(1, 9):
        if i + j < N_WEEKS and ratios[i + j] is not None:
            ratios[i + j] = min(0.97, ratios[i + j] + amt * float(np.exp(-(j - 1) / k)))


def run_plays(c, ratios, m, contacts, runs, emails):
    cid, tier = c["customer_id"], c["tier"]
    sched = {}

    def add(i, play):
        if i is not None:
            sched.setdefault(i, []).append(play)

    trig = c["signup"] + D(14)
    if tier != "CSM-led" and START <= trig <= SNAPSHOT and ("first_dashboard_created" not in m or m["first_dashboard_created"] > trig):
        add(widx(trig), ("onboarding_stall", trig))
    for k in contacts:
        if k["is_champion"] and k["left"] and START <= k["left"] + D(1) <= SNAPSHOT:
            add(widx(k["left"] + D(1)), ("champion_loss", k["left"] + D(1)))
    for a in c["anns"]:
        t = a - D(120)
        if START <= t <= SNAPSHOT and a > c["signup"] + D(200):
            add(widx(t), ("renewal_readiness", t))
    last = {}
    for w, d in enumerate(WEEKS):
        r = ratios[w]
        if r is None:
            continue
        plays = list(sched.get(w, []))
        age = (d - c["signup"]).days
        prev = ratios[w - 1] if w > 0 else None
        if tier != "CSM-led" and age > 42 and r < 0.40 and prev is not None and prev < 0.40 and \
                (d - last.get("adoption_nudge", date(2000, 1, 1))).days > 56:
            plays.append(("adoption_nudge", d))
        if r > 0.85 and prev is not None and prev > 0.85 and (d - last.get("expansion_signal", date(2000, 1, 1))).days > 90:
            plays.append(("expansion_signal", d))
        for play, td in plays:
            last[play] = td
            if play in ("adoption_nudge", "onboarding_stall"):
                group = "control" if rng.random() < 0.25 else "treated"
            else:
                group = "treated"
            variant = "control" if group == "control" else "standard"
            if play == "adoption_nudge" and group == "treated":
                variant = pick(["A", "B"])
            if group == "treated":
                amt = {"adoption_nudge": 0.11 if variant == "B" else 0.05, "onboarding_stall": 0.10,
                       "champion_loss": 0.03, "renewal_readiness": 0.03, "expansion_signal": 0.0}[play] * c["resp"]
                lift(ratios, w, amt)
            runs.append(dict(customer_id=cid, play_id=play, triggered_on=td, group=group, variant=variant,
                             tier=tier, w=w, before=float(np.mean([x for x in ratios[max(0, w - 2):w + 1] if x is not None]))))
            if group == "treated" and play != "expansion_signal":
                add_email(c, contacts, emails, play, variant, td)
    # fill outcomes (needs final ratios)
    for rr in runs:
        if rr.get("customer_id") != cid or "after" in rr:
            continue
        w = rr["w"]
        fut = [x for x in ratios[w + 1:w + 5] if x is not None]
        if len(fut) < 3:
            rr["after"], rr["delta"], rr["outcome"] = None, None, "pending"
        else:
            rr["after"] = float(np.mean(fut))
            rr["delta"] = rr["after"] - rr["before"]
            rr["outcome"] = "improved" if rr["delta"] >= 0.05 else "no_change"


# ---------------------------------------------------------------- email
EMAIL_N = [0]


def arc_mult(c, d):
    if c["onset"] and d >= c["onset"]:
        return {"quiet_fade": 0.25, "champion_loss": 0.30, "competitor_eval": 0.55, "support_friction": 0.5,
                "slow_onboarding_stall": 0.45}.get(c["arc"], 1.0)
    return 1.0


def add_email(c, contacts, emails, ctype, variant, d, subject=None, openmult=1.0, channel="email"):
    if not (START <= d <= SNAPSHOT) or (c["churn_date"] and d >= c["churn_date"]):
        return
    champ_gone = [x for x in contacts if x["is_champion"] and x["left"] and x["left"] <= d < x["left"] + D(21)]
    act = active_contacts(contacts, d)
    champs = [x for x in act if x["is_champion"]]
    bounced = False
    if champ_gone:
        rec, bounced = champ_gone[0], True
    elif champs:
        rec = champs[0]
    elif act:
        rec = act[0]
    else:
        return
    if subject is None:
        key = (ctype, variant)
        subject = T.SUBJECTS.get(key, T.SUBJECTS.get((ctype, 0), "Update from your customer success team"))
        subject = subject.format(industry=c["industry"].split(" and ")[0])
    sent = at(d, 9)
    p = float(np.clip(c["eng"] * arc_mult(c, d) * openmult, 0.02, 0.92))
    opened = (not bounced) and rng.random() < p
    clicked = opened and rng.random() < 0.3
    replied = opened and rng.random() < 0.05
    EMAIL_N[0] += 1
    emails.append(dict(email_id=f"E{EMAIL_N[0]:06d}", customer_id=c["customer_id"], contact_id=rec["contact_id"],
                       campaign_type=ctype, variant=variant, channel=channel, subject=subject, sent_at=sent,
                       bounced=bounced, opened=bool(opened),
                       opened_at=sent + timedelta(hours=float(rng.exponential(6))) if opened else None,
                       clicked=bool(clicked), replied=bool(replied)))
    return replied


def base_emails(c, contacts, emails, docs):
    sig = c["signup"]
    for k, off in enumerate([0, 3, 10, 21]):
        add_email(c, contacts, emails, "onboarding_series", k, sig + D(off))
    for mth in range(12):
        y, mo = (2025, 10 + mth) if mth < 3 else (2026, mth - 2)
        add_email(c, contacts, emails, "newsletter", 0, date(y, mo, 6)) if date(y, mo, 6) >= sig + D(14) else None


# ---------------------------------------------------------------- main
def main():
    os.makedirs(OUT, exist_ok=True)
    cust = build_customers()
    for c in cust:
        plan(c)
    R = {k: [] for k in ["contacts", "usage", "miles", "tickets", "emails", "nps", "inv", "events", "runs", "docs"]}
    doc_n = [0]

    def doc(cid, typ, d, role, src, title, text):
        doc_n[0] += 1
        R["docs"].append(dict(doc_id=f"D{doc_n[0]:06d}", customer_id=cid, doc_type=typ, doc_date=d,
                              author_role=role, source_id=src, title=title, text=text))

    tick_n = 0
    for c in cust:
        cid, arc, sig = c["customer_id"], c["arc"], c["signup"]
        contacts = make_contacts(c, R["contacts"])
        champ = contacts[0]
        m = make_milestones(c, R["miles"])
        ratios, seats = base_ratios(c, m)
        run_plays(c, ratios, m, contacts, R["runs"], R["emails"])
        c["last_ratio"], c["last_seats"] = next(((r, s) for r, s in zip(reversed(ratios), reversed(seats)) if r is not None), (0, 0))

        # usage rows
        for w, d in enumerate(WEEKS):
            r = ratios[w]
            if r is None:
                continue
            s = seats[w]
            au = int(round(s * r))
            age = max((d - sig).days / 7, 0)
            q = int(round(au * float(rng.lognormal(np.log(9), 0.45))))
            ai_share = float(np.clip(0.04 + 0.011 * w + rng.normal(0, 0.03), 0, 0.5))
            R["usage"].append(dict(
                customer_id=cid, week_start=d, seats_licensed=s, active_users=au, seat_utilisation=round(r, 4),
                sessions=int(au * rng.poisson(3.2)), queries=q, ai_assistant_queries=int(q * ai_share),
                dashboards_viewed=int(au * rng.lognormal(np.log(6), 0.4)),
                dashboards_created=int(rng.poisson(max(0.05, au * 0.18))),
                features_used=int(np.clip(round(2 + r * 7 + rng.normal(0, 0.8)), 1, 10)),
                data_sources_connected=int(min(1 + age / 9, 6)) if au else 1))

        # contract events
        for typ, d, delta in c["events"]:
            R["events"].append(dict(customer_id=cid, event_type=typ, event_date=d, arr_delta=delta,
                                    reason=c["churn_reason"] if typ == "churn" else None))

        # base emails
        base_emails(c, contacts, R["emails"], R["docs"])

        # tickets
        obj = pick(T.OBJECTS[c["industry"]])
        src = pick(T.SOURCES)
        supp = pick(SUPPORT_NAMES)
        for w, d in enumerate(WEEKS):
            r = ratios[w]
            if r is None or d < sig:
                continue
            lam = (0.02 + 0.011 * np.sqrt(seats[w])) * (0.6 + r) * {"Digital": 0.9, "Pooled": 1.0, "CSM-led": 1.2}[c["tier"]]
            fr = arc == "support_friction" and c["onset"] and c["onset"] - W(6) <= d <= c["onset"] + W(8)
            if fr:
                lam *= 5
            if arc == "slow_onboarding_stall":
                lam *= 1.8
            if arc == "competitor_eval" and c["onset"] and d >= c["onset"] - W(8):
                lam *= 1.6
            if arc == "quiet_fade" and c["onset"] and d >= c["onset"]:
                lam *= 0.5
            for _ in range(int(rng.poisson(min(lam, 3)))):
                p = np.array([.15, .20, .12, .25, .15, .05, .08])
                if fr:
                    p *= [1.6, 2.2, 1, 1, 2, 1, 1]
                if arc == "competitor_eval":
                    p *= [1, 2.5, 1, 1, 1, 1, 2]
                if arc == "slow_onboarding_stall":
                    p *= [2, 1, 1, 2, 1, 1, 1]
                cat = pick(T.TICKET_CATEGORIES, p / p.sum())
                created = at(d + D(rng.integers(0, 5)))
                base = {"CSM-led": 2.5, "Pooled": 5, "Digital": 9}[c["tier"]] * (2.2 if fr else 1)
                frh = float(rng.lognormal(np.log(base), 0.6))
                res = float(rng.lognormal(np.log(30), 0.8)) * (2 if cat in ("Bug", "Performance") else 1)
                reop = int(rng.poisson(0.9 if fr else 0.12))
                esc = bool(rng.random() < (0.4 if reop >= 2 else 0.22 if fr else 0.04))
                resolved = created + timedelta(hours=frh + res + 30 * reop)
                status = "resolved" if resolved <= datetime(2026, 10, 5) else "open"
                tick_n += 1
                tid = f"T{tick_n:06d}"
                who = active_contacts(contacts, created.date())
                who = pick(who) if who else champ
                tags = []
                if arc == "competitor_eval" and c["onset"] and d >= c["onset"] - W(4) and rng.random() < 0.5:
                    tags.append("competitor")
                if arc == "champion_loss" and champ["left"] and d >= champ["left"] and rng.random() < 0.6:
                    tags.append("new_owner")
                if arc != "competitor_eval" and rng.random() < 0.015:
                    tags.append("comp_past")
                if frh > 12:
                    tags.append("slow")
                subj = T.ticket_subject(rng, cat, obj, src)
                R["tickets"].append(dict(
                    ticket_id=tid, customer_id=cid, contact_id=who["contact_id"], created_at=created, category=cat,
                    priority=pick(["Low", "Medium", "High"], [.4, .45, .15]), subject=subj,
                    first_response_hours=round(frh, 1), resolved_at=resolved if status == "resolved" else None,
                    status=status, reopen_count=reop, escalated=esc))
                doc(cid, "ticket_thread", created.date(), "customer+support", tid, subj,
                    T.ticket_text(rng, cat, obj, src, who["name"], supp, reop, tags, old=champ["name"], comp=c["comp"]))

        # call notes, QBR notes, exit/save notes
        end = c["churn_date"] or SNAPSHOT
        csm = c["csm"]
        step = {"CSM-led": 4, "Pooled": 10}.get(c["tier"])
        if step:
            d = max(START, sig + D(14)) + D(rng.integers(0, 14))
            while d < end:
                ph = phase(c, d)
                idx = widx(d)
                rat = ratios[idx] if idx is not None and ratios[idx] is not None else 0.5
                if ph == "ok":
                    kind = "renewal" if any(0 < (a - d).days <= 120 for a in c["anns"]) else \
                        "expansion" if rat > 0.85 else "ok"
                else:
                    kind = {"ok_dip": "ok_dip", "concern": "concern", "critical": "critical", "recovering": "recovering"}[ph]
                doc(cid, "call_note", d, f"CSM ({csm})", f"{cid}-CALL-{d.isoformat()}", f"Call note {d.isoformat()}",
                    T.call_note(rng, kind, arc, c["company_name"], obj, champ["name"], c["comp"]))
                d += W(step) + D(rng.integers(0, 6))
        if c["tier"] != "Digital" and (c["band"] == "Whale" or c["tier"] == "CSM-led" or c["band"] == "Mid"):
            d = START + D(rng.integers(20, 90))
            while d < end:
                ph = phase(c, d)
                ph = "ok" if ph in ("ok_dip",) else ph
                doc(cid, "qbr_note", d, f"CSM ({csm})", f"{cid}-QBR-{d.isoformat()}", f"QBR {d.isoformat()}",
                    T.qbr_note(rng, ph, c["company_name"], obj))
                add_email(c, contacts, R["emails"], "csm_outreach", 0, d - D(3))
                d += W(13)
        if c["saved"] and c["onset"] and c["onset"] + W(15) <= SNAPSHOT:
            d = c["onset"] + W(15)
            doc(cid, "call_note", d, f"CSM ({csm})", f"{cid}-SAVE", "Save outcome",
                T.call_note(rng, "save", arc, c["company_name"], obj, champ["name"], c["comp"]))
        if c["churn_date"]:
            reason_arc = arc if arc in CHURN_P else "surprise"
            doc(cid, "call_note", c["churn_date"], f"CSM ({csm})", f"{cid}-EXIT", "Exit note",
                T.call_note(rng, "exit", reason_arc, c["company_name"], obj, champ["name"], c["comp"]))

        # NPS
        for sd in [date(2025, 12, 15), date(2026, 3, 16), date(2026, 6, 15), date(2026, 9, 14)]:
            if sd < sig + D(60) or (c["churn_date"] and sd >= c["churn_date"]):
                continue
            ph = phase(c, sd)
            if rng.random() > (0.25 if ph in ("concern", "critical") else 0.42):
                continue
            score = int(np.clip(round(rng.normal({"ok": 8.6, "ok_dip": 8, "recovering": 7.5, "concern": 5.5, "critical": 3.5}[ph], 1.4)), 0, 10))
            who = pick(active_contacts(contacts, sd) or [champ])
            comment = T.nps_comment(rng, score, arc, ph) if rng.random() < 0.7 else None
            rid = f"N{len(R['nps']) + 1:05d}"
            R["nps"].append(dict(response_id=rid, customer_id=cid, contact_id=who["contact_id"], survey_date=sd,
                                 score=score, comment=comment))
            if comment:
                doc(cid, "nps_comment", sd, "customer", rid, f"NPS {score}", comment)

        # invoices
        for k in range(12):
            y, mo = (2025, 11 + k) if k < 2 else (2026, k - 1)
            inv = date(y, mo, 1)
            if inv < sig or (c["churn_date"] and inv >= c["churn_date"]):
                continue
            ph = phase(c, inv)
            late = int(rng.poisson({"concern": 9, "critical": 14}.get(ph, 0.4)))
            paid = inv + D(30 + late)
            R["inv"].append(dict(
                invoice_id=f"I{len(R['inv']) + 1:06d}", customer_id=cid, invoice_date=inv, amount=round(arr_at(c, inv) / 12, 2),
                due_date=inv + D(30), paid_date=paid if paid <= SNAPSHOT else None, days_late=late,
                status="paid" if paid <= SNAPSHOT else ("overdue" if inv + D(30) < SNAPSHOT else "open"),
                disputed=bool(ph == "critical" and rng.random() < 0.2)))

    # ---- customers table
    rows, gt = [], []
    for c in cust:
        churned = c["churn_date"] is not None
        nxt = next((a for a in c["anns"] + [c["anns"][-1] + D(365)] if a > SNAPSHOT), None)
        age = (SNAPSHOT - c["signup"]).days
        if churned:
            stage = "Churned"
        elif age < 90:
            stage = "Onboarding"
        elif nxt and (nxt - SNAPSHOT).days <= 120:
            stage = "Renewal"
        elif c["last_ratio"] > 0.8 and c["arc"] == "healthy_expanding":
            stage = "Expansion"
        else:
            stage = "Adoption"
        rows.append(dict(
            customer_id=c["customer_id"], company_name=c["company_name"], industry=c["industry"], use_case=c["use_case"],
            region=c["region"], size_band=c["band"], tier=c["tier"], csm_owner=c["csm"], signup_date=c["signup"],
            arr_at_signup=c["arr0"], arr_current=0.0 if churned else round(c["arr_now"], 2),
            seats_current=0 if churned else c["last_seats"], status="churned" if churned else "active",
            churn_date=c["churn_date"], next_renewal_date=None if churned else nxt, lifecycle_stage=stage))
        gt.append(dict(customer_id=c["customer_id"], arc=c["arc"], onset_date=c["onset"], saved=c["saved"],
                       churn_reason=c["churn_reason"], target_renewal=c["target_renewal"]))

    # ---- play runs and catalog
    runs = []
    for i, r in enumerate(R["runs"], 1):
        runs.append(dict(run_id=f"R{i:05d}", customer_id=r["customer_id"], play_id=r["play_id"],
                         triggered_on=r["triggered_on"], experiment_group=r["group"], variant=r["variant"],
                         utilisation_before=round(r["before"], 4),
                         utilisation_after_4w=None if r.get("after") is None else round(r["after"], 4),
                         delta_4w=None if r.get("delta") is None else round(r["delta"], 4), outcome=r["outcome"]))
    catalog = pd.DataFrame(PLAYS, columns=["play_id", "name", "trigger_rule", "coverage"])

    def save(name, data):
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
        df.to_csv(os.path.join(OUT, f"{name}.csv"), index=False)
        print(f"{name:24s}{len(df):>8,d} rows")

    save("customers", rows)
    save("contacts", R["contacts"])
    save("weekly_usage", R["usage"])
    save("onboarding_milestones", R["miles"])
    save("tickets", R["tickets"])
    save("email_events", R["emails"])
    save("nps_responses", R["nps"])
    save("invoices", R["inv"])
    save("contract_events", R["events"])
    save("play_catalog", catalog)
    save("play_runs", runs)
    save("documents", R["docs"])
    save("ground_truth", gt)


if __name__ == "__main__":
    main()
