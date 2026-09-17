# Project context

This is a small FastAPI application (an in-memory bookstore API). Tests use pytest.

## How to run things
- Start the app:   `uvicorn main:app --reload`
- Run the tests:   `pytest -q`

## Conventions
- The app lives in `main.py`. The FastAPI instance is `app`.
- Test files live in `tests/`, named `test_*.py`.
- Test the API through FastAPI's `TestClient` (from `fastapi.testclient`), not by
  starting a live server.
- When asked ONLY to write tests, do not modify application code in `main.py`.

## Endpoints
- `GET  /`                 health check
- `GET  /books`            list all books
- `GET  /books/search?q=`  search books by title substring
- `GET  /books/{book_id}`  get one book (404 if missing)
- `POST /books`            create a book (price must be > 0)
- `DELETE /books/{book_id}` delete a book (404 if missing)
- `POST /orders/quote`     price an order (bulk discount + shipping rules)
