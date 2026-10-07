"""Flask API for the dashboard and the copilot.

Run:  python server.py        (http://localhost:5001)
The dashboard (Vite, port 5173) is the only allowed browser origin.
"""
import uuid

from flask import Flask, jsonify, request
from flask_cors import CORS

import demo_copilot
import llm
import queries as Q
import tools as T
from db import APP_DB, ROOT, app_db

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])
_sessions = {}


@app.get("/api/health")
def health():
    return jsonify(ok=True, anthropic_key_set=llm.key_set(), model=llm.MODEL,
                   vector_index_ready=(ROOT / "data" / "chroma").exists() and (ROOT / "data" / "search.db").exists())


@app.get("/api/overview")
def overview():
    return jsonify(Q.overview())


@app.get("/api/customers")
def customers():
    a = request.args
    return jsonify(Q.customers(a.get("tier"), a.get("stage"), a.get("industry"), a.get("band"), a.get("flag"),
                               a.get("renewal_within"), a.get("search"), a.get("sort", "health_score"), a.get("order", "asc"),
                               min(int(a.get("limit", 100)), 300)))


@app.get("/api/customers/<cid>")
def customer(cid):
    d = Q.customer_detail(cid)
    return (jsonify(d), 200) if d else (jsonify(error=f"No customer {cid}"), 404)


@app.get("/api/cohorts")
def cohorts():
    return jsonify(Q.cohorts())


@app.get("/api/rfm")
def rfm():
    return jsonify(Q.rfm(request.args.get("segment")))


@app.get("/api/plays")
def plays():
    return jsonify(Q.plays())


@app.get("/api/alerts")
def alerts():
    return jsonify(Q.alerts())


@app.get("/api/program-impact")
def program_impact():
    return jsonify(Q.program_impact())


@app.get("/api/copilot/tools")
def copilot_tools():
    return jsonify(T.catalog())


@app.get("/api/copilot/demo-questions")
def demo_questions():
    return jsonify(demo=not llm.key_set(), questions=[{"id": e["id"], "question": e["question"]} for e in demo_copilot.load()])


@app.get("/api/customers/<cid>/outreach-draft")
def outreach_draft(cid):
    if llm.key_set():
        out = T.draft_outreach(cid)
        return jsonify(out) if "error" not in out else (jsonify(out), 404)
    out = demo_copilot.template_draft(cid)
    return jsonify(out) if "error" not in out else (jsonify(out), 404)


@app.post("/api/copilot")
def copilot():
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify(error="Send JSON like {\"question\": \"...\", \"session_id\": \"optional\"}"), 400
    if not llm.key_set():
        # Demo mode: replay recorded sessions whose tool calls and numbers were computed from the real data.
        entries = demo_copilot.load()
        e = next((x for x in entries if x["id"] == body.get("demo_id")), None) or demo_copilot.match(question, entries)
        if e:
            return jsonify(demo=True, answer=e["answer"], trace=e["trace"], question=e["question"])
        return jsonify(demo=True, trace=[], answer="Demo mode: no API key is set, so I can only answer the recorded questions. Try one of: "
                       + "; ".join(x["question"] for x in entries))
    from copilot import CopilotSession
    sid = body.get("session_id") or str(uuid.uuid4())
    if sid not in _sessions:
        _sessions[sid] = CopilotSession()
    try:
        out = _sessions[sid].ask(question)
    except Exception as e:
        return jsonify(error=f"Copilot error: {type(e).__name__}: {e}"), 502
    return jsonify(session_id=sid, **out)


@app.post("/api/approvals")
def queue_approval():
    b = request.get_json(silent=True) or {}
    if not b.get("customer_id") or not b.get("body"):
        return jsonify(error="customer_id and body are required"), 400
    con = app_db()
    cur = con.execute("INSERT INTO approvals (customer_id, kind, subject, body) VALUES (?,?,?,?)",
                      (b["customer_id"], b.get("kind", "outreach"), b.get("subject", ""), b["body"]))
    con.commit()
    return jsonify(approval_id=cur.lastrowid, status="pending", note="Queued for human approval. Nothing is sent.")


@app.get("/api/approvals")
def approvals():
    con = app_db()
    rows = [dict(r) for r in con.execute("SELECT * FROM approvals ORDER BY approval_id DESC LIMIT 50")]
    rules = [dict(r) for r in con.execute("SELECT * FROM alert_rules ORDER BY rule_id DESC LIMIT 50")]
    return jsonify(approvals=rows, alert_rules=rules, note="Recorded only. Nothing is sent externally until n8n is connected.")


if __name__ == "__main__":
    app.run(port=5001, debug=False)
