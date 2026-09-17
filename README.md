# Tiny Bookstore API

A small FastAPI app to practice an agentic-coding workflow: generate a test
suite with Claude Code, run pytest automatically via a hook, and triage failures
headlessly in CI.

## Run it locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pytest

uvicorn main:app --reload          # visit http://127.0.0.1:8000/docs
```

`http://127.0.0.1:8000/docs` gives you an interactive UI to poke every endpoint.

## Endpoints

| Method | Path                | Notes                                   |
|--------|---------------------|-----------------------------------------|
| GET    | `/`                 | health check                            |
| GET    | `/books`            | list all books                          |
| GET    | `/books/search?q=`  | search by title substring               |
| GET    | `/books/{book_id}`  | one book, 404 if missing                |
| POST   | `/books`            | create; `price` must be > 0 (else 422)  |
| DELETE | `/books/{book_id}`  | delete, 204 on success, 404 if missing  |
| POST   | `/orders/quote`     | price an order (discount + shipping)    |

### Order pricing rules (good test + bug-planting territory)
- Subtotal over **$100** → 10% discount.
- Post-discount total of **$50 or more** → free shipping, otherwise **$5.99**.

## The project workflow

1. **Generate tests** — run `claude`, ask it to write a pytest suite in `tests/`
   covering each endpoint's happy path plus error cases. Review what it writes.
2. **Hook** — `.claude/settings.json` runs `pytest` after every edit, so Claude
   sees breakages immediately. Type `/hooks` in a session to confirm it loaded.
3. **CI triage** — push to your own GitHub repo, add an `ANTHROPIC_API_KEY`
   secret, and open a PR inside your repo. `.github/workflows/test-and-triage.yml`
   runs the tests and, on failure, posts a comment explaining the root cause.

## Demo a failing test

Plant a bug to see the CI triage fire. Easy options in `main.py`:
- Change the discount threshold `> 100` to `>= 100`.
- Change free-shipping `>= 50` to `> 50`.
- Remove a `round(...)` call so totals drift by a cent.

Write (or keep) a test that asserts the *correct* behavior, open a PR, and watch
the job go red with a Claude comment naming the cause.
