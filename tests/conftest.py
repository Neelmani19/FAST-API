import copy

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(autouse=True)
def reset_store():
    """Restore the in-memory store after every test.

    `main.books` and `main._next_id` are module-level globals, so anything a
    test creates or deletes would otherwise leak into the tests that follow.
    """
    saved_books = copy.deepcopy(main.books)
    saved_next_id = main._next_id
    yield
    main.books.clear()
    main.books.update(saved_books)
    main._next_id = saved_next_id


@pytest.fixture()
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def make_book(client):
    """Create a book through the API and return it."""

    def _make_book(title="A Test Book", author="A Test Author", price=10.0):
        response = client.post(
            "/books", json={"title": title, "author": author, "price": price}
        )
        assert response.status_code == 201
        return response.json()

    return _make_book
