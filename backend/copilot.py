"""Health Copilot: Claude tool-use loop over the toolbox in tools.py.

The model sees the tool catalog, decides what to call, we run the tool, feed the result back, and repeat until it can
answer (or hits the turn cap). Conversation history is kept per session so follow-ups have context.
The client is injectable so the loop can be tested without an API key.

Run:  python copilot.py     (interactive test; needs ANTHROPIC_API_KEY in backend/.env)
"""
import json

import llm
import tools as T

MAX_TOOL_TURNS = 5
MAX_HISTORY = 12   # messages kept per session

SYSTEM = """You are the Customer Health Copilot for the Tech Touch customer success team of a B2B analytics SaaS company. \
Today is 2026-10-05. Answer questions about customer health, risk, adoption, support, renewals, cohorts and lifecycle plays \
using ONLY the tools provided. Never invent numbers, customers, quotes or outcomes.

How to work:
- Cite the concrete numbers and customer ids the tools return. Keep answers short: the answer first, then the one-line reason.
- Health flags: Healthy 75 and above, Watch 60 to 74, At risk below 60. The score comes from five dimensions (adoption, support, engagement, commercial, onboarding).
- For anything about what customers said, use search_documents. For competitor mentions pass the competitor names and words such as competitor, vendor, switching as keywords.
  Mentions can be noise (for example a past purchase comparison), so read the text before concluding a customer is at risk, and say so when the evidence is thin.
- Drafts are drafts. Never say a message was sent. Use send_for_approval only when the user asks to queue something. Alert rules and handoffs are only recorded, not executed.
- If no tool covers the question, say so plainly instead of guessing. Churn and expansion prediction models are not built yet.
- This is a plain-text chat window. Do not use Markdown tables, headers or asterisks. Short paragraphs and simple dashed lists only."""


def _blocks(content):
    out = []
    for b in content:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
    return out


def _summary(name, result):
    if isinstance(result, dict) and "error" in result:
        return f"error: {result['error']}"
    if isinstance(result, dict):
        for k in ("customers", "results", "accounts", "similar", "top", "weeks_newest_first", "groups"):
            if isinstance(result.get(k), list):
                return f"{len(result[k])} {k}"
        return ", ".join(list(result)[:4])
    return str(result)[:60]


class CopilotSession:
    def __init__(self, client=None):
        self.client = client or llm.get_client()
        self.history = []
        self.tokens = {"input": 0, "output": 0}

    def ask(self, question):
        msgs = self.history + [{"role": "user", "content": question}]
        trace = []
        for turn in range(MAX_TOOL_TURNS + 1):
            last = turn == MAX_TOOL_TURNS
            kw = {} if last else {"tools": T.schemas()}
            r = self.client.messages.create(model=llm.MODEL, max_tokens=1500, system=SYSTEM, messages=msgs, **kw)
            self.tokens["input"] += getattr(r.usage, "input_tokens", 0)
            self.tokens["output"] += getattr(r.usage, "output_tokens", 0)
            msgs.append({"role": "assistant", "content": _blocks(r.content)})
            if r.stop_reason != "tool_use" or last:
                answer = "".join(b.text for b in r.content if b.type == "text").strip()
                self.history = msgs[-MAX_HISTORY:]
                while self.history and self.history[0]["role"] != "user" or (self.history and isinstance(self.history[0]["content"], list)):
                    self.history = self.history[1:]   # keep history starting at a plain user turn
                return {"answer": answer, "trace": trace, "tool_turns": turn, "tokens": dict(self.tokens)}
            results = []
            for b in r.content:
                if b.type == "tool_use":
                    res = T.run(b.name, b.input)
                    trace.append({"tool": b.name, "kind": T.TOOLS[b.name][0] if b.name in T.TOOLS else "unknown",
                                  "input": b.input, "summary": _summary(b.name, res)})
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(res, default=str)[:12000]})
            msgs.append({"role": "user", "content": results})


if __name__ == "__main__":
    s = CopilotSession()
    print("Health Copilot. Ctrl+C to quit.")
    while True:
        out = s.ask(input("\n> "))
        for t in out["trace"]:
            print(f"  tool: {t['tool']}({json.dumps(t['input'])}) -> {t['summary']}")
        print("\n" + out["answer"])
