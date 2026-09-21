# Eval harness for the triage agent

This measures whether the triage agent actually works — and lets you prove that
a change (new prompt, new model, new tools) made it **better**, not worse. It is
"CI for the agent," the same way pytest is CI for the app.

## The idea in one line
You can't trust an agent because its answer *reads* well. You trust it because
it scores well against cases where you already know the correct answer.

## What's here
- `cases/` — labeled scenarios. Each is a fixed failing (or passing) test run
  plus the **known-correct** diagnosis (category, file, root cause). This is the
  ground truth everything rests on.
- `triage.py` — two model calls: one that diagnoses a case into structured JSON,
  and an "LLM-as-judge" that scores the free-text root cause against the truth.
- `run_evals.py` — runs every case, scores it, and prints a scorecard.
- `report.json` — written after each run, for CI to keep.

## Run it
```bash
pip install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

python evals/run_evals.py                 # full run with the judge
python evals/run_evals.py --no-judge      # cheaper: score category + file only
python evals/run_evals.py --threshold 0.8 # exit 1 if under 80% (used in CI)
python evals/run_evals.py --repeat 3      # run each case 3x to check consistency
```

## Reading the scorecard
- **Category accuracy** — did it pick app_bug / test_bug / environment / flake / no_bug correctly?
- **Localization** — did it name the right file?
- **Root-cause accuracy** — does its explanation match the known cause (judged)?
- **False positives** — it flagged a problem when there was none. Erodes trust.
- **False negatives** — it missed a real bug. Worse than nothing. Tracked separately
  on purpose, because the two errors have very different costs.

## The categories
| category      | meaning                                                        |
|---------------|----------------------------------------------------------------|
| `app_bug`     | the application code is wrong                                  |
| `test_bug`    | the app is correct; the test asserts the wrong thing           |
| `environment` | tests couldn't run (imports, paths, config, missing deps)      |
| `flake`       | intermittent failure, not a code defect (timing, rendering)    |
| `no_bug`      | everything passed; nothing to fix                              |

## How to improve the agent over time
1. Change ONE lever: the triage prompt in `triage.py`, the model (`EVAL_MODEL`),
   or the tools/context the agent gets.
2. Re-run the evals.
3. Keep the change only if the score went up. Never ship a change that lowers it.

## How to grow the eval set (the flywheel)
Every time the agent gets a real failure wrong in production, add that failure
here as a new case with its correct answer. The eval set grows toward the
failures you actually hit, so the agent gets measurably better at *your* work.

## Honest limitations of this starter
- Inputs are **frozen** scenarios so scoring is repeatable. A fuller setup would
  also eval the whole tool-using agent end to end.
- The **LLM judge** must be sanity-checked against human labels before you trust
  it — spot-check its PASS/FAIL calls on a sample.
- Eight cases is a demo. Real coverage needs enough cases to mirror your true mix
  of UI-flow and business-rule failures, including the hard, ambiguous ones.
