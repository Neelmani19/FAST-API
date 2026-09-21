"""
mini_agent.py — a tiny agent you can actually read and understand.

The whole "magic" of an AI agent is ONE loop:

    1. Send the conversation (+ the list of tools) to the model.
    2. The model either answers, or asks to use a tool.
    3. If it asked for a tool, YOUR code runs the tool and sends the result back.
    4. Repeat until the model stops asking for tools.

That's it. Everything else (frameworks, orchestration) is decoration on top
of this loop. This file implements it from scratch with three real tools that
tie into the test project: list files, read a file, and run pytest.

Run it:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."
    python mini_agent.py "Look at this project, run the tests, and tell me if anything is broken and why."
"""

import os
import sys
import glob
import subprocess

import anthropic

# A Sonnet-class model is a good speed/cost balance for an agent.
# Switch to a Haiku model if you want it cheaper; an Opus model if you want it smarter.
MODEL = "claude-sonnet-5"

# Guard rail: never let the loop run forever. If the agent hasn't finished in
# this many steps, we stop. Runaway loops are the #1 way agents burn money.
MAX_ITERATIONS = 15

# Only let the agent touch files inside the folder we launch it from.
ROOT = os.path.abspath(os.getcwd())


# ---------------------------------------------------------------------------
# 1. THE TOOLS — plain Python functions. The model never runs these itself;
#    it only *asks* us to, and our code decides whether/how to run them.
# ---------------------------------------------------------------------------

def _safe_path(path: str) -> str:
    """Resolve a path and refuse anything outside ROOT (stops '../../etc/passwd')."""
    full = os.path.abspath(os.path.join(ROOT, path))
    if not full.startswith(ROOT):
        raise ValueError(f"Refused: '{path}' is outside the project directory.")
    return full


def list_files(directory: str = ".") -> str:
    base = _safe_path(directory)
    hits = glob.glob(os.path.join(base, "**", "*"), recursive=True)
    files = [os.path.relpath(h, ROOT) for h in hits if os.path.isfile(h)]
    files = [f for f in files if "/.git/" not in f and "__pycache__" not in f]
    return "\n".join(sorted(files)) or "(no files found)"


def read_file(path: str) -> str:
    full = _safe_path(path)
    with open(full, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    # Cap the size so one huge file can't blow up the context (and your bill).
    return text[:10000]


def run_pytest(args: str = "") -> str:
    """Run pytest in the project and return its output."""
    cmd = [sys.executable, "-m", "pytest"] + (args.split() if args else [])
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
    output = (proc.stdout + proc.stderr)[-6000:]  # keep the tail; that's where failures are
    return f"(exit code {proc.returncode})\n{output}"


# The registry: maps the tool NAME the model uses to the actual function.
TOOL_FUNCTIONS = {
    "list_files": list_files,
    "read_file": read_file,
    "run_pytest": run_pytest,
}

# ---------------------------------------------------------------------------
# 2. THE TOOL SCHEMAS — how we DESCRIBE those tools to the model. The model
#    reads these descriptions to decide which tool to call and with what
#    arguments. Good descriptions = good tool use. This is prompt engineering.
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "list_files",
        "description": "List the files in the project (recursively). Use this first to see what exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Subdirectory to list. Defaults to the project root."}
            },
        },
    },
    {
        "name": "read_file",
        "description": "Read the text contents of a single file so you can understand the code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file, relative to the project root."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_pytest",
        "description": "Run the project's pytest test suite and get the output, including any failures.",
        "input_schema": {
            "type": "object",
            "properties": {
                "args": {"type": "string", "description": "Optional extra pytest arguments, e.g. '-v' or 'tests/test_quote.py'."}
            },
        },
    },
]

SYSTEM_PROMPT = """You are a coding agent working inside a Python project.
Work step by step: explore the files, read what's relevant, run the tests, and
reason about the results. When you reach a conclusion, state it clearly and stop.
Do not guess about code you have not read — use your tools to check."""


# ---------------------------------------------------------------------------
# 3. THE LOOP — this is the entire agent. Read it slowly; it's the whole idea.
# ---------------------------------------------------------------------------

def run_agent(goal: str) -> None:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    messages = [{"role": "user", "content": goal}]

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n===== step {step} =====")

        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Show whatever the model said out loud this turn.
        for block in response.content:
            if block.type == "text":
                print(block.text)

        # IMPORTANT: append the model's turn verbatim so the tool_use ids line up.
        messages.append({"role": "assistant", "content": response.content})

        # If the model didn't ask for a tool, it's finished. Exit the loop.
        if response.stop_reason != "tool_use":
            final_text = "\n".join(b.text for b in response.content if b.type == "text")
            report_file = os.environ.get("AGENT_REPORT_FILE")
            if report_file:                       # only in CI, where we set this
                with open(report_file, "w", encoding="utf-8") as f:
                    f.write(final_text)
            print("\n----- agent finished -----")
            return

        # Otherwise: run every tool the model asked for, collect the results.
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            print(f"  -> calling tool: {block.name}({block.input})")
            try:
                output = TOOL_FUNCTIONS[block.name](**block.input)
                is_error = False
            except Exception as e:  # a failing tool is data for the model, not a crash
                output = f"Tool error: {e}"
                is_error = True
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
                "is_error": is_error,
            })

        # Feed the tool results back in as the next user message, and loop.
        messages.append({"role": "user", "content": tool_results})

    print("\n[stopped: hit the max-iteration guard rail]")


if __name__ == "__main__":
    goal = " ".join(sys.argv[1:]) or "List the files, read the app, run the tests, and report anything broken and why."
    run_agent(goal)
