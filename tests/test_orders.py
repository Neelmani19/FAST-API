import pytest

# Seeded prices, for readability in the expectations below.
PRAGMATIC = 39.99  # id 1
CLEAN_CODE = 32.50  # id 2
FLUENT_PYTHON = 54.00  # id 3

DISCOUNT_RATE = 0.10
SHIPPING_FEE = 5.99


def quote(client, items):
    return client.post("/orders/quote", json={"items": items})


# ---- Happy paths ----------------------------------------------------------


def test_quote_small_order_pays_shipping_and_gets_no_discount(client):
    response = quote(client, [{"book_id": 2, "quantity": 1}])

    assert response.status_code == 200
    assert response.json() == {
        "subtotal": pytest.approx(32.50),
        "discount": pytest.approx(0.0),
        "shipping": pytest.approx(SHIPPING_FEE),
        "total": pytest.approx(38.49),
    }


def test_quote_mid_sized_order_gets_free_shipping_but_no_discount(client):
    # 54.00 clears the $50 free-shipping bar but not the $100 discount bar.
    response = quote(client, [{"book_id": 3, "quantity": 1}])

    assert response.status_code == 200
    body = response.json()
    assert body["subtotal"] == pytest.approx(54.00)
    assert body["discount"] == pytest.approx(0.0)
    assert body["shipping"] == pytest.approx(0.0)
    assert body["total"] == pytest.approx(54.00)


def test_quote_large_order_gets_discount_and_free_shipping(client):
    response = quote(client, [{"book_id": 3, "quantity": 2}])  # 108.00

    assert response.status_code == 200
    assert response.json() == {
        "subtotal": pytest.approx(108.00),
        "discount": pytest.approx(10.80),
        "shipping": pytest.approx(0.0),
        "total": pytest.approx(97.20),
    }


def test_quote_sums_multiple_line_items(client):
    response = quote(
        client, [{"book_id": 1, "quantity": 1}, {"book_id": 2, "quantity": 1}]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["subtotal"] == pytest.approx(PRAGMATIC + CLEAN_CODE)
    assert body["discount"] == pytest.approx(0.0)
    assert body["shipping"] == pytest.approx(0.0)
    assert body["total"] == pytest.approx(72.49)


def test_quote_multiplies_by_quantity(client):
    one = quote(client, [{"book_id": 2, "quantity": 1}]).json()
    three = quote(client, [{"book_id": 2, "quantity": 3}]).json()

    assert three["subtotal"] == pytest.approx(one["subtotal"] * 3)


def test_quote_includes_a_newly_created_book(client, make_book):
    created = make_book(title="Priced Book", price=20.0)

    body = quote(client, [{"book_id": created["id"], "quantity": 2}]).json()

    assert body["subtotal"] == pytest.approx(40.0)


# ---- Rule boundaries ------------------------------------------------------


def test_subtotal_of_exactly_100_gets_no_discount(client, make_book):
    """The discount applies when subtotal > 100, so 100.00 itself does not."""
    created = make_book(title="Exactly One Hundred", price=100.0)

    body = quote(client, [{"book_id": created["id"], "quantity": 1}]).json()

    assert body["subtotal"] == pytest.approx(100.0)
    assert body["discount"] == pytest.approx(0.0)
    assert body["shipping"] == pytest.approx(0.0)
    assert body["total"] == pytest.approx(100.0)


def test_subtotal_just_over_100_gets_the_discount(client, make_book):
    created = make_book(title="Just Over", price=100.01)

    body = quote(client, [{"book_id": created["id"], "quantity": 1}]).json()

    assert body["discount"] == pytest.approx(round(100.01 * DISCOUNT_RATE, 2))


def test_total_of_exactly_50_ships_free(client, make_book):
    """Shipping is free once the post-discount total *reaches* 50."""
    created = make_book(title="Exactly Fifty", price=50.0)

    body = quote(client, [{"book_id": created["id"], "quantity": 1}]).json()

    assert body["shipping"] == pytest.approx(0.0)
    assert body["total"] == pytest.approx(50.0)


def test_total_just_under_50_pays_shipping(client, make_book):
    created = make_book(title="Just Under Fifty", price=49.99)

    body = quote(client, [{"book_id": created["id"], "quantity": 1}]).json()

    assert body["shipping"] == pytest.approx(SHIPPING_FEE)
    assert body["total"] == pytest.approx(55.98)


def test_discount_can_drop_an_order_back_under_the_shipping_threshold(client, make_book):
    """Subtotal 101 earns a 10.10 discount, leaving 90.90 -- still free shipping."""
    created = make_book(title="Hundred And One", price=101.0)

    body = quote(client, [{"book_id": created["id"], "quantity": 1}]).json()

    assert body["discount"] == pytest.approx(10.10)
    assert body["shipping"] == pytest.approx(0.0)
    assert body["total"] == pytest.approx(90.90)


def test_quote_with_no_items_is_an_empty_order(client):
    body = quote(client, []).json()

    assert body == {
        "subtotal": pytest.approx(0.0),
        "discount": pytest.approx(0.0),
        "shipping": pytest.approx(SHIPPING_FEE),
        "total": pytest.approx(SHIPPING_FEE),
    }


# ---- Error cases ----------------------------------------------------------


def test_quote_unknown_book_returns_404(client):
    response = quote(client, [{"book_id": 9999, "quantity": 1}])

    assert response.status_code == 404
    assert response.json()["detail"] == "Book 9999 not found"


def test_quote_404s_even_when_other_items_are_valid(client):
    response = quote(
        client, [{"book_id": 1, "quantity": 1}, {"book_id": 9999, "quantity": 1}]
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Book 9999 not found"


def test_quote_for_a_deleted_book_returns_404(client, make_book):
    created = make_book()
    assert client.delete(f"/books/{created['id']}").status_code == 204

    response = quote(client, [{"book_id": created["id"], "quantity": 1}])

    assert response.status_code == 404


@pytest.mark.parametrize("quantity", [0, -1])
def test_quote_rejects_non_positive_quantity(client, quantity):
    response = quote(client, [{"book_id": 1, "quantity": quantity}])

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing "items"
        {"items": "not-a-list"},
        {"items": [{"book_id": 1}]},  # missing quantity
        {"items": [{"quantity": 1}]},  # missing book_id
        {"items": [{"book_id": "one", "quantity": 1}]},
        {"items": [{"book_id": 1, "quantity": 1.5}]},
    ],
)
def test_quote_rejects_invalid_payloads(client, payload):
    response = client.post("/orders/quote", json=payload)

    assert response.status_code == 422
