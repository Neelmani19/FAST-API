import pytest

import main


# ---- GET /books -----------------------------------------------------------


def test_list_books_returns_seeded_books(client):
    response = client.get("/books")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(main.books)
    assert {b["id"] for b in body} == set(main.books)
    assert body[0] == {
        "id": 1,
        "title": "The Pragmatic Programmer",
        "author": "Hunt & Thomas",
        "price": 39.99,
    }


def test_list_books_includes_a_newly_created_book(client, make_book):
    created = make_book(title="Brand New")

    titles = [b["title"] for b in client.get("/books").json()]

    assert "Brand New" in titles
    assert created["id"] in {b["id"] for b in client.get("/books").json()}


# ---- GET /books/{book_id} -------------------------------------------------


def test_get_book_returns_the_requested_book(client):
    response = client.get("/books/2")

    assert response.status_code == 200
    assert response.json() == {
        "id": 2,
        "title": "Clean Code",
        "author": "Robert Martin",
        "price": 32.50,
    }


def test_get_book_missing_id_returns_404(client):
    response = client.get("/books/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Book not found"


def test_get_book_non_integer_id_returns_422(client):
    response = client.get("/books/not-an-int")

    assert response.status_code == 422


# ---- POST /books ----------------------------------------------------------


def test_create_book_returns_201_and_the_stored_book(client):
    payload = {"title": "Test Driven Development", "author": "Kent Beck", "price": 44.95}

    response = client.post("/books", json=payload)

    assert response.status_code == 201
    created = response.json()
    assert created["id"] not in (1, 2, 3)
    assert created == {"id": created["id"], **payload}

    # The book is really persisted, not just echoed back.
    fetched = client.get(f"/books/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_create_book_assigns_increasing_ids(client, make_book):
    first = make_book(title="First")
    second = make_book(title="Second")

    assert second["id"] > first["id"]


@pytest.mark.parametrize("price", [0, -1, -0.01])
def test_create_book_rejects_non_positive_price(client, price):
    response = client.post(
        "/books", json={"title": "Free Book", "author": "Nobody", "price": price}
    )

    assert response.status_code == 422
    assert "Free Book" not in [b["title"] for b in client.get("/books").json()]


@pytest.mark.parametrize(
    "payload",
    [
        {"author": "No Title", "price": 10.0},
        {"title": "No Author", "price": 10.0},
        {"title": "No Price", "author": "Someone"},
        {"title": "", "author": "Empty Title", "price": 10.0},
        {"title": "Empty Author", "author": "", "price": 10.0},
        {"title": "Bad Price", "author": "Someone", "price": "cheap"},
    ],
)
def test_create_book_rejects_invalid_payloads(client, payload):
    response = client.post("/books", json=payload)

    assert response.status_code == 422


# ---- DELETE /books/{book_id} ----------------------------------------------


def test_delete_book_returns_204_and_removes_it(client, make_book):
    created = make_book(title="Doomed")

    response = client.delete(f"/books/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/books/{created['id']}").status_code == 404


def test_delete_book_missing_id_returns_404(client):
    response = client.delete("/books/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Book not found"


def test_delete_book_twice_returns_404_the_second_time(client, make_book):
    created = make_book()

    assert client.delete(f"/books/{created['id']}").status_code == 204
    assert client.delete(f"/books/{created['id']}").status_code == 404
