import pytest


def test_search_matches_a_title_substring(client):
    response = client.get("/books/search", params={"q": "Clean"})

    assert response.status_code == 200
    body = response.json()
    assert [b["title"] for b in body] == ["Clean Code"]


@pytest.mark.parametrize("q", ["python", "PYTHON", "PyThOn"])
def test_search_is_case_insensitive(client, q):
    response = client.get("/books/search", params={"q": q})

    assert response.status_code == 200
    assert [b["title"] for b in response.json()] == ["Fluent Python"]


def test_search_can_match_several_books(client, make_book):
    make_book(title="Practical Python")

    titles = [b["title"] for b in client.get("/books/search", params={"q": "python"}).json()]

    assert sorted(titles) == ["Fluent Python", "Practical Python"]


def test_search_matches_on_title_only_not_author(client):
    # "Ramalho" is an author, never a title.
    response = client.get("/books/search", params={"q": "Ramalho"})

    assert response.status_code == 200
    assert response.json() == []


def test_search_with_no_matches_returns_empty_list(client):
    response = client.get("/books/search", params={"q": "zzz-no-such-title"})

    assert response.status_code == 200
    assert response.json() == []


def test_search_route_is_not_shadowed_by_the_book_id_route(client):
    """`/books/search` must resolve to the search handler, not `book_id="search"`."""
    response = client.get("/books/search", params={"q": "code"})

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_search_without_query_param_returns_422(client):
    response = client.get("/books/search")

    assert response.status_code == 422
