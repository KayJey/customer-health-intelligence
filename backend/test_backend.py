"""Backend checks. Run:  python test_backend.py
Covers every endpoint and the copilot tool-use loop (with a scripted fake model, so no API key is needed)."""
from types import SimpleNamespace as NS

import copilot
import server


def block_text(t):
    return NS(type="text", text=t)


def block_tool(i, name, inp):
    return NS(type="tool_use", id=i, name=name, input=inp)


class FakeClient:
    """Plays a fixed script: call a tool, then answer from its result."""
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        content, stop = self.script.pop(0)
        return NS(content=content, stop_reason=stop, usage=NS(input_tokens=100, output_tokens=20))


def main():
    c = server.app.test_client()
    ok = 0
    for path in ["/api/health", "/api/overview", "/api/customers?flag=At risk&limit=5", "/api/customers/C0018", "/api/cohorts",
                 "/api/rfm?segment=Cannot lose", "/api/plays", "/api/alerts", "/api/program-impact", "/api/copilot/tools", "/api/approvals"]:
        r = c.get(path)
        assert r.status_code == 200, (path, r.status_code, r.data[:200])
        ok += 1
    assert c.get("/api/customers/NOPE").status_code == 404
    print(f"{ok} GET endpoints ok, 404 handled")

    r = c.post("/api/copilot", json={"question": "hi"})
    j = r.get_json()
    assert r.status_code == 200 and j["demo"] and "recorded questions" in j["answer"]
    r = c.post("/api/copilot", json={"question": "Which customers are at risk this month?"})
    j = r.get_json()
    assert j["demo"] and j["trace"][0]["tool"] == "query_customers" and "At risk" in j["answer"]
    r = c.post("/api/copilot", json={"question": "anything about renewals coming up?"})
    assert r.get_json()["trace"][0]["tool"] == "get_renewal_pipeline"
    assert len(c.get("/api/copilot/demo-questions").get_json()["questions"]) == 9
    d = c.get("/api/customers/C0169/outreach-draft").get_json()
    assert "DRAFT" in d["status"] and d["body"]
    print("demo-mode copilot ok (matched, trace shown, free text falls back)")

    # copilot loop with a fake model: question -> tool call -> result -> answer
    fake = FakeClient([
        ([block_text("Let me check."), block_tool("t1", "query_customers", {"health_flag": "At risk", "limit": 3})], "tool_use"),
        ([block_tool("t2", "get_health_breakdown", {"customer_id": "C0018", "weeks": 2})], "tool_use"),
        ([block_text("Three accounts are at risk. C0018 is the largest.")], "end_turn"),
    ])
    s = copilot.CopilotSession(client=fake)
    out = s.ask("Which customers are at risk?")
    assert out["tool_turns"] == 2 and [t["tool"] for t in out["trace"]] == ["query_customers", "get_health_breakdown"], out
    assert "C0018" in out["answer"]
    # tool results were passed back to the model as tool_result blocks
    results = [m["content"][0] for m in fake.calls[-1]["messages"] if m["role"] == "user" and isinstance(m["content"], list)]
    assert [r["type"] for r in results] == ["tool_result", "tool_result"]
    assert "customers" in results[0]["content"] and "weeks_newest_first" in results[1]["content"]
    print("copilot loop ok:", [(t["tool"], t["summary"]) for t in out["trace"]], "| tokens", out["tokens"])

    # follow-up keeps history; an unknown tool is handled
    fake.script = [([block_tool("t3", "no_such_tool", {})], "tool_use"), ([block_text("I could not do that.")], "end_turn")]
    out2 = s.ask("And what about renewals?")
    assert out2["trace"][0]["kind"] == "unknown" and "error" in out2["trace"][0]["summary"]
    assert any(m["role"] == "user" and m["content"] == "Which customers are at risk?" for m in fake.calls[-1]["messages"])
    print("follow-up keeps context, unknown tool handled")

    # turn cap: a model that never stops calling tools still ends with an answer
    loop = [([block_tool(f"x{i}", "get_alerts_digest", {"limit": 1})], "tool_use") for i in range(copilot.MAX_TOOL_TURNS)]
    loop.append(([block_text("Here is what I have.")], "end_turn"))
    fake.script = loop
    out3 = s.ask("keep going")
    assert out3["answer"] == "Here is what I have." and "tools" not in fake.calls[-1]
    print("turn cap ok (final call made without tools)")
    print("\nALL BACKEND CHECKS PASSED")


if __name__ == "__main__":
    main()
