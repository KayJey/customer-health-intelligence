"""Claude client helper. The API key comes from backend/.env (never committed)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")


def key_set():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def get_client():
    if not key_set():
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Copy backend/.env.example to backend/.env and add your key.")
    from anthropic import Anthropic
    return Anthropic()


def complete(system, user, max_tokens=700, client=None):
    c = client or get_client()
    r = c.messages.create(model=MODEL, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in r.content if b.type == "text").strip()
