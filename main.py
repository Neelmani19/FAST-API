from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Tiny Bookstore API")

# ---- In-memory data store -------------------------------------------------
# Seeded so the app has something to serve on startup. Resets every restart.
books: dict[int, dict] = {
    1: {"id": 1, "title": "The Pragmatic Programmer", "author": "Hunt & Thomas", "price": 39.99},
    2: {"id": 2, "title": "Clean Code", "author": "Robert Martin", "price": 32.50},
    3: {"id": 3, "title": "Fluent Python", "author": "Luciano Ramalho", "price": 54.00},
}
_next_id = 4


# ---- Schemas --------------------------------------------------------------
class BookIn(BaseModel):
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    price: float = Field(gt=0)  # price must be positive


class Book(BookIn):
    id: int


class QuoteItem(BaseModel):
    book_id: int
    quantity: int = Field(gt=0)


class QuoteRequest(BaseModel):
    items: list[QuoteItem]


class QuoteResponse(BaseModel):
    subtotal: float
    discount: float
    shipping: float
    total: float


# ---- Routes ---------------------------------------------------------------
@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/books", response_model=list[Book])
def list_books():
    return list(books.values())


# NOTE: this MUST be declared before /books/{book_id}, otherwise "search"
# gets captured as a book_id path parameter. A nice thing to understand.
@app.get("/books/search", response_model=list[Book])
def search_books(q: str):
    q_lower = q.lower()
    return [b for b in books.values() if q_lower in b["title"].lower()]


@app.get("/books/{book_id}", response_model=Book)
def get_book(book_id: int):
    book = books.get(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


@app.post("/books", response_model=Book, status_code=201)
def create_book(payload: BookIn):
    global _next_id
    book = {"id": _next_id, **payload.model_dump()}
    books[_next_id] = book
    _next_id += 1
    return book


@app.delete("/books/{book_id}", status_code=204)
def delete_book(book_id: int):
    if book_id not in books:
        raise HTTPException(status_code=404, detail="Book not found")
    del books[book_id]
    return None


@app.post("/orders/quote", response_model=QuoteResponse)
def quote_order(request: QuoteRequest):
    """Calculate the price of an order.

    Business rules:
      * Orders with a subtotal over $100 get a 10% discount.
      * Shipping is free once the post-discount total reaches $50, else $5.99.
    """
    subtotal = 0.0
    for item in request.items:
        book = books.get(item.book_id)
        if book is None:
            raise HTTPException(status_code=404, detail=f"Book {item.book_id} not found")
        subtotal += book["price"] * item.quantity

    discount = round(subtotal * 0.10, 2) if subtotal > 100 else 0.0
    discounted = subtotal - discount
    shipping = 0.0 if discounted >= 50 else 5.99
    total = round(discounted + shipping, 2)

    return QuoteResponse(
        subtotal=round(subtotal, 2),
        discount=discount,
        shipping=shipping,
        total=total,
    )
