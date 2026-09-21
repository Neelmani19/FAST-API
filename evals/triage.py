"""
triage.py — the two model calls the eval harness needs.

1. triage_case(): given a FIXED failing-test scenario (test output + code
   context), ask the model to diagnose it and return a STRUCTURED result.
   Structured output is the trick that makes grading mechanical instead of
   "read it and see if it looks right."

2. judge_root_cause(): an "LLM-as-judge" — a second model call that scores
   whether the agent's free-text explanation matches the known-correct one.
   You must sanity-check a judge against human labels before trusting it.

Why fixed input? Evals need a stable, repeatable input so a score means
something. So here we freeze each scenario instead of letting the agent run
pytest live (which would be non-deterministic and hard to score).
"""

import os
import json
import anthropic

MODEL = os.environ.get("EVAL_MODEL", "claude-sonnet-5")  # Haiku is cheaper; Opus is smarter
_client = anthropic.Anthropic()

CATEGORIES = ["app_bug", "test_bug", "environment", "flake", "no_bug"]

TRIAGE_SYSTEM = """You are a test-failure triage assistant.
You are given the output of a test run and some relevant code/context.
Decide what is going on and reply with ONLY a JSON object — no prose, no code fences:

{
  "category": one of "app_bug" | "test_bug" | "environment" | "flake" | "no_bug",
  "file": the single most relevant file path, or null,
  "line": an approximate line number as an integer, or null,
  "root_cause": one or two sentences, or "" if nothing is wrong
}

How to decide the category:
- Judge behaviour against the stated requirement/spec, NOT against what the code happens to do.
- "app_bug": the application code is wrong.
- "test_bug": the application is correct but the test asserts the wrong thing.
- "environment": tests could not run properly due to setup/config/tooling (imports, paths, missing deps).
- "flake": an intermittent failure unrelated to a code defect (timing, rendering, network).
- "no_bug": everything passed; nothing to fix.
"""


def _extract_json(text: str) -> dict:
    """Pull the first {...} object out of the model's reply, tolerating stray fences."""
    text = text.strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:]
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {"category": "parse_error", "file": None, "line": None, "root_cause": text[:200]}


def triage_case(case_input: dict) -> dict:
    """Send one fixed scenario to the model; return {result, tokens}."""
    user = (
        f"TEST OUTPUT:\n{case_input.get('pytest_output', '')}\n\n"
        f"CODE / CONTEXT:\n{case_input.get('code_context', '')}"
    )
    resp = _client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=TRIAGE_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    usage = getattr(resp, "usage", None)
    tokens = (usage.input_tokens + usage.output_tokens) if usage else 0
    return {"result": _extract_json(text), "tokens": tokens}


JUDGE_SYSTEM = """You compare two explanations of why a test failed.
Reply with ONLY one word: PASS or FAIL.
PASS = the candidate explanation identifies the SAME underlying root cause as the reference.
FAIL = it identifies a different or wrong cause.
Wording will differ — judge the substance, not the phrasing."""


def judge_root_cause(reference: str, candidate: str) -> bool:
    """LLM-as-judge: does the candidate explanation match the reference cause?"""
    resp = _client.messages.create(
        model=MODEL,
        max_tokens=8,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": f"REFERENCE:\n{reference}\n\nCANDIDATE:\n{candidate}"}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip().upper()
    return text.startswith("PASS")
