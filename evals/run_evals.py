"""
run_evals.py — run the triage agent against every labeled case and score it.

This is "CI for the agent." It turns agent quality into a NUMBER you can watch
over time and defend against regressions. Run it whenever you change the triage
prompt, the model, or the tools:

    python evals/run_evals.py                 # full run, with the LLM judge
    python evals/run_evals.py --no-judge      # cheaper: score category + file only
    python evals/run_evals.py --threshold 0.8 # exit 1 if under 80% (use this in CI)
    python evals/run_evals.py --repeat 3      # run each case 3x to check consistency
"""

import os
import sys
import json
import glob
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from triage import triage_case, judge_root_cause  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CASES_DIR = os.path.join(HERE, "cases")


def load_cases():
    cases = []
    for path in sorted(glob.glob(os.path.join(CASES_DIR, "*.json"))):
        with open(path, encoding="utf-8") as f:
            cases.append(json.load(f))
    return cases


def basename(p):
    return os.path.basename(p).lower() if p else None


def score_case(case: dict, pred: dict, use_judge: bool) -> dict:
    """Compare one prediction against the known-correct answer."""
    exp = case["expected"]

    cat_ok = pred.get("category") == exp["category"]

    # Localization only counts when the case actually points at a file.
    if exp.get("file"):
        loc_applicable, loc_ok = True, basename(pred.get("file")) == basename(exp["file"])
    else:
        loc_applicable, loc_ok = False, True

    # Root cause only counts when there's something to explain and the judge is on.
    if exp["category"] != "no_bug" and use_judge:
        rc_applicable = True
        rc_ok = judge_root_cause(exp.get("root_cause", ""), pred.get("root_cause", ""))
    else:
        rc_applicable, rc_ok = False, True

    passed = cat_ok and loc_ok and rc_ok

    # The two error types have very different costs — track them apart.
    false_positive = exp["category"] == "no_bug" and pred.get("category") not in ("no_bug", None)
    false_negative = exp["category"] in ("app_bug", "test_bug") and pred.get("category") == "no_bug"

    return {
        "cat_ok": cat_ok, "loc_ok": loc_ok, "loc_applicable": loc_applicable,
        "rc_ok": rc_ok, "rc_applicable": rc_applicable,
        "passed": passed, "fp": false_positive, "fn": false_negative,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-judge", action="store_true", help="skip the LLM judge (score category + file only)")
    ap.add_argument("--threshold", type=float, default=None, help="exit 1 if overall accuracy below this (e.g. 0.8)")
    ap.add_argument("--repeat", type=int, default=1, help="run each case N times to measure consistency")
    args = ap.parse_args()
    use_judge = not args.no_judge

    cases = load_cases()
    if not cases:
        print(f"No eval cases found in {CASES_DIR}")
        sys.exit(1)

    rows, total_tokens = [], 0
    t0 = time.time()
    for case in cases:
        preds, toks = [], 0
        for _ in range(max(1, args.repeat)):
            out = triage_case(case["input"])
            preds.append(out["result"])
            toks += out["tokens"]
        total_tokens += toks
        pred = preds[0]  # score the first run; use the rest to measure agreement
        agreement = sum(1 for p in preds if p.get("category") == pred.get("category")) / len(preds)
        rows.append((case, pred, score_case(case, pred, use_judge), agreement))

    elapsed = time.time() - t0

    total = len(rows)
    passes = sum(1 for _, _, sc, _ in rows if sc["passed"])
    cat = sum(1 for _, _, sc, _ in rows if sc["cat_ok"])
    loc_app = [sc for _, _, sc, _ in rows if sc["loc_applicable"]]
    loc = sum(1 for sc in loc_app if sc["loc_ok"])
    rc_app = [sc for _, _, sc, _ in rows if sc["rc_applicable"]]
    rc = sum(1 for sc in rc_app if sc["rc_ok"])
    fps = sum(1 for _, _, sc, _ in rows if sc["fp"])
    fns = sum(1 for _, _, sc, _ in rows if sc["fn"])

    # ---- scorecard ----
    print("\n================ EVAL SCORECARD ================")
    for case, pred, sc, agreement in rows:
        mark = "PASS" if sc["passed"] else "FAIL"
        exp = case["expected"]
        extra = "" if args.repeat == 1 else f"   agreement {agreement * 100:.0f}%"
        print(f"[{mark}] {case['id']}  ({case.get('kind', '?')})")
        print(f"        category  expected={exp['category']:<12} got={str(pred.get('category')):<12}{extra}")
        if not sc["passed"]:
            print(f"        file      expected={exp.get('file')}  got={pred.get('file')}")
            print(f"        expected cause: {exp.get('root_cause', '')[:90]}")
            print(f"        got cause:      {str(pred.get('root_cause', ''))[:90]}")
    print("------------------------------------------------")
    print(f"Overall accuracy (full pass): {passes}/{total} = {passes / total * 100:.0f}%")
    print(f"Category accuracy:            {cat}/{total} = {cat / total * 100:.0f}%")
    if loc_app:
        print(f"Localization accuracy:        {loc}/{len(loc_app)} = {loc / len(loc_app) * 100:.0f}%")
    if rc_app:
        print(f"Root-cause accuracy (judge):  {rc}/{len(rc_app)} = {rc / len(rc_app) * 100:.0f}%")
    print(f"False positives (cried wolf): {fps}   <- erodes trust")
    print(f"False negatives (missed bug): {fns}   <- worse than nothing")
    print(f"Tokens used: {total_tokens}   Wall time: {elapsed:.1f}s")
    print("================================================\n")

    report = {
        "total": total, "full_pass": passes, "category_correct": cat,
        "localization": {"correct": loc, "applicable": len(loc_app)},
        "root_cause": {"correct": rc, "applicable": len(rc_app)},
        "false_positives": fps, "false_negatives": fns,
        "tokens": total_tokens, "seconds": round(elapsed, 1),
        "cases": [
            {"id": c["id"], "expected": c["expected"]["category"],
             "got": p.get("category"), "passed": sc["passed"]}
            for c, p, sc, _ in rows
        ],
    }
    with open(os.path.join(HERE, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    if args.threshold is not None and passes / total < args.threshold:
        print(f"BELOW THRESHOLD {args.threshold:.0%} — blocking this change.")
        sys.exit(1)


if __name__ == "__main__":
    main()
