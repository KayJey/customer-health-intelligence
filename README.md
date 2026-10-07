# Customer Health Intelligence

A prototype of a customer-health program for a fictional B2B analytics SaaS "Tech Touch" segment:
health scoring beyond login frequency, AI-assisted risk alerting, lifecycle plays, cohort and RFM
analysis, and a tool-using AI copilot (SQL + vector search + actions).

Status: design mock (`mock/`), synthetic data generator (`generator/`), health score + cohorts + RFM (`analytics/`),
BigQuery load (dataset `customer_health`), Flask backend + copilot toolbox (`backend/`) and React dashboard (`dashboard/`) are done.
The copilot runs in demo mode without an API key. Next: n8n alerts and the live ThoughtSpot connection.

**All data is synthetic.** No real company, customer, person or employer data is used.
The signal types mirror client-intelligence work done earlier (cases, turnaround time, rework,
escalations, email engagement), re-shaped for a SaaS customer-success setting.

Demo video (about 1.5 minutes, shows the live ThoughtSpot embeds): link to be added.

## Quick start: run the app

| What | Port | URL | Folder |
|---|---|---|---|
| Backend API (Flask) | 5001 | http://localhost:5001/api/health | `backend/` |
| Dashboard (React + Vite) | 5173 | http://localhost:5173 | `dashboard/` |
| Design mock (optional, static) | 8080 | http://localhost:8080 | `mock/` |

The dashboard calls `/api/...` on its own port and Vite forwards it to the backend on 5001, so **both servers must be running**.
Open the dashboard at port 5173.

**One-time setup** (skip what is already done):
```bash
pip install -r backend/requirements.txt
cd dashboard && npm install && cd ..
```
The data and indexes already exist in `data/` once you have run the generator, analytics and `build_vector_index.py` steps below.
On a fresh clone, run those first (they are about 4 minutes in total):
```bash
cd generator && python generate.py && cd ..
cd analytics && python run_analytics.py && cd ..
cd backend && python build_vector_index.py && python demo_copilot.py && cd ..
```

**Every time you run it** (two terminals, both from the project root):

Terminal 1, backend:
```bash
cd backend
python server.py
```
Check it: http://localhost:5001/api/health should show `"ok": true`.

Terminal 2, dashboard:
```bash
cd dashboard
npm run dev
```
Then open http://localhost:5173.

**Stop:** press Ctrl+C in each terminal.

**Optional: the static design mock**
```bash
cd mock
python -m http.server 8080
```
Open http://localhost:8080. Do not double-click `index.html`: some previews do not run its JavaScript.

**Check everything works:** `cd backend && python test_backend.py` should end with `ALL BACKEND CHECKS PASSED`.

**Troubleshooting**
- Dashboard shows "Could not load data ... Is the backend running on port 5001?": start Terminal 1 first.
- "Address already in use" on 5001 or 5173: another copy is running. Close it, or find it with `netstat -ano | findstr :5001` and stop that process id.
- Copilot says "Demo mode": expected without an API key. It replays recorded questions that were computed from the real data.
- To use a live copilot: copy `backend/.env.example` to `backend/.env`, add `ANTHROPIC_API_KEY`, and restart the backend. Never commit `.env`.
- Search or copilot errors about a missing index: run `python backend/build_vector_index.py`.

## Mock
Open `mock/index.html` through a local server (`python -m http.server 8080` inside `mock/`).
It is a clickable prototype with fake numbers and pre-written copilot answers.

## Generate the data
```bash
cd generator
pip install -r requirements.txt
python generate.py      # writes data/csv/*.csv  (seeded, so it is reproducible)
python validate.py      # checks that the story arcs show up in the numbers
```

## What is simulated
250 customers, 52 weekly snapshots (2025-10-06 to 2026-09-28, snapshot date 2026-10-05).

Size cohorts: 130 SME, 95 Mid, 25 Whales. Coverage tiers: Digital, Pooled, CSM-led.

Each customer is given one hidden **story arc** (saved only in `ground_truth.csv`):

| Arc | What happens |
|---|---|
| healthy_steady | Ramps up, stable usage, a rare surprise churn with no warning |
| healthy_expanding | Seat utilisation rises, mid-term seat expansion |
| late_bloomer | Slow start, then ramps up |
| false_alarm | A 6-week usage dip that recovers (so alerts are not trivially right) |
| slow_onboarding_stall | Never reaches first value, quiet churn or a late save |
| champion_loss | The champion leaves, emails bounce, usage collapses; sometimes saved by a replacement |
| support_friction | Ticket spike, reopens, escalations, slow responses, then usage fades |
| competitor_eval | Competitor mentions in tickets and notes, flat decline, renewal risk |
| quiet_fade | Gradual decay, ignored emails, hard to reach |

Risky arcs churn only at a renewal date, and only some of them (the rest are saved or still pending
at the snapshot), so the data contains customers who are at risk right now.

## Tables (`data/csv`)

| Table | Rows | Purpose |
|---|---|---|
| customers | 250 | Master: industry, size band, tier, CSM, ARR, seats, lifecycle stage, status, renewal date |
| contacts | ~780 | People per account with role, champion and exec-sponsor flags, joined and left dates |
| weekly_usage | ~10.5K | Weekly seats, active users, utilisation, sessions, queries, AI queries, dashboards, features, data sources |
| onboarding_milestones | ~970 | data_connected, first_search, first_dashboard_created, shared_by_second_user (time to first value) |
| tickets | ~1.1K | Support tickets with category, first response time, reopens, escalation |
| email_events | ~3.5K | Sends, opens, clicks, replies, bounces by campaign, play and A/B variant |
| nps_responses | ~300 | Quarterly NPS with comments |
| invoices | ~2.4K | Monthly invoices with days late, overdue and disputed flags |
| contract_events | ~415 | New, renewal, expansion, contraction, churn with ARR change |
| play_catalog | 5 | Onboarding stall, adoption nudge, champion loss, renewal readiness, expansion signal |
| play_runs | ~530 | Play triggers with treated or control group, variant, 4-week outcome |
| documents | ~2.4K | **Unstructured text** for the vector store: ticket threads, CSM call notes, QBR notes, NPS comments |
| ground_truth | 250 | Hidden arcs (validation only, not loaded to BigQuery by default) |

Notes on realism:
- Competitor mentions also appear at healthy accounts ("we compared this with X before buying"), so
  keyword search alone is not enough and the copilot has to reason about context.
- The adoption-nudge test has a 25 percent control group and A/B variants (generic vs industry-personalised).
- Text is template-based (deterministic and free). An LLM pass can enrich it later.
- Any model trained on this data learns the generator's rules. Do not report accuracy as a headline
  number; use a time-based split and report precision and recall as a method demo.

## Health score, cohorts and RFM
```bash
cd analytics
python run_analytics.py     # about 2 minutes; writes health_weekly, health_current, cohort and RFM tables + data/health.db
python validate_health.py   # checks the score against the hidden story arcs
```
Method and results: `docs/health-score-methodology.md`. Headline: on synthetic data the score drops
below 60 before churn for 96% of churned customers (median 7 weeks ahead).

## Backend (Flask API + AI copilot)
```bash
cd backend
pip install -r requirements.txt
python build_vector_index.py     # once: embeds tickets and notes (Chroma) + keyword index (SQLite FTS5), about 2 minutes
copy .env.example .env           # then add ANTHROPIC_API_KEY (needed only for the copilot chat and outreach drafts)
python test_backend.py           # endpoints + copilot loop checks (no API key needed)
python server.py                 # http://localhost:5001
```
Endpoints: `/api/overview`, `/api/customers`, `/api/customers/<id>`, `/api/cohorts`, `/api/rfm`, `/api/plays`,
`/api/alerts`, `/api/program-impact`, `/api/copilot/tools`, `POST /api/copilot`, `/api/approvals`, `/api/health`.

The copilot is a Claude tool-use loop over 16 tools (SQL, hybrid vector + keyword search, compute, LLM, record-only actions).
It answers only from tool results, caps at 5 tool turns, and never sends anything: outreach is a draft, and alert rules
and handoffs are only recorded in `data/app.db` until n8n is connected. Competitor mentions use hybrid search because
a small embedding model alone blurred them with similar text.

## Dashboard (React + Vite + Recharts)
```bash
# terminal 1
cd backend && python server.py          # http://localhost:5001
# terminal 2
cd dashboard && npm install && npm run dev   # http://localhost:5173 (proxies /api to the backend)
```
Screens: portfolio overview, customers, customer detail (score breakdown, history, usage, recommended action,
draft outreach with a queue-for-approval step), cohorts and RFM, journeys and plays, alerts, program impact (metrics,
experiment results, a clearly labelled scenario), AI copilot, copilot tools, and ThoughtSpot integration (design and status).

**Demo mode:** with no `ANTHROPIC_API_KEY` the copilot replays recorded questions (`backend/demo_copilot.json`).
The tool calls and every number are computed by the real tools on the dataset; the wording is templated, not LLM-written.
Regenerate with `python backend/demo_copilot.py`. Add a key to `backend/.env` for live answers.

## Load into BigQuery
```bash
pip install -r generator/requirements.txt
gcloud auth application-default login
python generator/load_bigquery.py --project YOUR_PROJECT_ID
```
