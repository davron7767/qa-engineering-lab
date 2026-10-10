"""Server-rendered web UI. Uses the same service layer as the REST API, so business rules
cannot drift between the two interfaces."""

import secrets
import uuid
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.errors import AppError, AuthenticationRequired
from app.models import User
from app.schemas.common import page_count
from app.security import csrf_token, csrf_valid
from app.services import auth as auth_service
from app.services import orders as order_service
from app.services import products as product_service
from app.services.rules import MAX_QUANTITY_PER_LINE, OrderLine

SESSION_COOKIE = "qa_session"
ORDER_HISTORY_PAGE_SIZE = 10

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
templates.env.filters["money"] = lambda v: f"${v:,.2f}"

router = APIRouter(include_in_schema=False)


class LoginRedirect(Exception):
    def __init__(self, next_path: str) -> None:
        self.next_path = next_path


def safe_next(path: str | None) -> str:
    """Only allow local absolute paths, preventing open redirects (e.g. //evil.example)."""
    if path and path.startswith("/") and not path.startswith("//") and "\\" not in path:
        return path
    return "/products"


def current_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        return auth_service.resolve_session(db, token).user
    except AuthenticationRequired:
        return None


def render(
    request: Request,
    template: str,
    user: User | None,
    status_code: int = 200,
    **context: Any,
) -> HTMLResponse:
    token = request.cookies.get(SESSION_COOKIE)
    csrf = csrf_token(get_settings().secret_key, token) if user and token else ""
    return templates.TemplateResponse(
        request,
        template,
        {"user": user, "csrf_token": csrf, **context},
        status_code=status_code,
    )


def require_user(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if user is None:
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        raise LoginRedirect(target)
    return user


def check_csrf(request: Request, submitted: str | None) -> None:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not csrf_valid(get_settings().secret_key, token, submitted):
        raise AppError("Your form has expired. Please reload the page and try again.")


def login_redirect(next_path: str) -> RedirectResponse:
    return RedirectResponse(f"/login?next={quote(next_path)}", status_code=303)


def register_web_handlers(app: FastAPI) -> None:
    @app.exception_handler(LoginRedirect)
    async def _to_login(_request: Request, exc: LoginRedirect) -> RedirectResponse:
        return login_redirect(exc.next_path)


def not_found_page(request: Request) -> HTMLResponse:
    return render(request, "not_found.html", None, status_code=404)


DbDep = Annotated[Session, Depends(get_db)]


@router.get("/")
def home() -> RedirectResponse:
    return RedirectResponse("/products", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: DbDep, next: str | None = None) -> Response:
    user = current_user(request, db)
    if user:
        return RedirectResponse(safe_next(next), status_code=303)
    return render(request, "login.html", None, next=safe_next(next))


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    db: DbDep,
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/products",
) -> Response:
    if not email.strip() or not password:
        return render(
            request,
            "login.html",
            None,
            status_code=422,
            error="Email and password are required.",
            email=email,
            next=safe_next(next),
        )
    try:
        user = auth_service.authenticate(db, email, password)
    except AppError:
        return render(
            request,
            "login.html",
            None,
            status_code=401,
            error="Invalid email or password.",
            email=email,
            next=safe_next(next),
        )
    issued = auth_service.issue_session(db, user)
    response = RedirectResponse(safe_next(next), status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=get_settings().session_ttl_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
    )
    return response


@router.post("/logout")
def logout(request: Request, db: DbDep, csrf_token: Annotated[str, Form()] = "") -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token and csrf_valid(get_settings().secret_key, token, csrf_token):
        auth_service.revoke_session(db, token)
    response = RedirectResponse("/login?logged_out=1", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/products", response_class=HTMLResponse)
def products_page(
    request: Request, db: DbDep, q: str | None = Query(None, max_length=100)
) -> Response:
    filters = product_service.ProductFilters(search=q or None)
    rows, _total = product_service.list_products(db, filters, page=1, page_size=100)
    return render(request, "products.html", current_user(request, db), products=rows, q=q or "")


@router.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: int, db: DbDep) -> Response:
    user = current_user(request, db)
    try:
        product = product_service.get_product(db, product_id)
    except AppError:
        return render(request, "not_found.html", user, status_code=404, what="Product")
    return render(
        request,
        "product_detail.html",
        user,
        product=product,
        idempotency_key=uuid.uuid4().hex,
        max_quantity=MAX_QUANTITY_PER_LINE,
    )


def _new_order_form(
    request: Request, db: Session, user: User, status_code: int = 200, **context: Any
) -> HTMLResponse:
    rows, _ = product_service.list_products(
        db, product_service.ProductFilters(active=True), page=1, page_size=100
    )
    return render(
        request,
        "order_new.html",
        user,
        status_code=status_code,
        products=rows,
        idempotency_key=uuid.uuid4().hex,
        max_quantity=MAX_QUANTITY_PER_LINE,
        values=context.pop("values", {}),
        **context,
    )


@router.get("/orders/new", response_class=HTMLResponse)
def new_order_page(request: Request, db: DbDep) -> Response:
    user = require_user(request, db)
    return _new_order_form(request, db, user)


def parse_quantities(form: dict[str, str]) -> tuple[list[OrderLine], list[str]]:
    """Read qty_<product_id> fields. Blank or 0 means 'not ordered'."""
    lines: list[OrderLine] = []
    errors: list[str] = []
    for key, raw in form.items():
        if not key.startswith("qty_"):
            continue
        value = raw.strip()
        if value in ("", "0"):
            continue
        try:
            product_id = int(key.removeprefix("qty_"))
            quantity = int(value)
        except ValueError:
            errors.append(f"Quantity '{value}' is not a whole number.")
            continue
        if quantity < 1:
            errors.append("Quantity must be at least 1.")
        elif quantity > MAX_QUANTITY_PER_LINE:
            errors.append(f"Quantity must not exceed {MAX_QUANTITY_PER_LINE}.")
        else:
            lines.append(OrderLine(product_id, quantity))
    if not lines and not errors:
        errors.append("Select at least one product by entering a quantity.")
    return lines, errors


def describe_error(exc: AppError) -> str:
    if exc.code == "INSUFFICIENT_INVENTORY":
        parts = [
            f"{d['sku']}: requested {d['requested']}, only {d['available']} available"
            for d in exc.details
        ]
        return "Insufficient inventory. " + "; ".join(parts) + "."
    return exc.message + "."


@router.post("/orders", response_class=HTMLResponse)
async def place_order(request: Request, db: DbDep) -> Response:
    user = require_user(request, db)
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    values = {k: v for k, v in form.items() if k.startswith("qty_")}
    try:
        check_csrf(request, form.get("csrf_token"))
    except AppError as exc:
        return _new_order_form(request, db, user, 400, errors=[exc.message], values=values)
    lines, errors = parse_quantities(form)
    if errors:
        return _new_order_form(request, db, user, 422, errors=errors, values=values)
    key = form.get("idempotency_key") or secrets.token_hex(16)
    try:
        placed = order_service.create_order(db, user, lines, key[:64])
    except AppError as exc:
        return _new_order_form(
            request, db, user, exc.status_code, errors=[describe_error(exc)], values=values
        )
    return RedirectResponse(f"/orders/{placed.order.id}?placed=1", status_code=303)


@router.get("/orders", response_class=HTMLResponse)
def order_history(request: Request, db: DbDep, page: int = Query(1, ge=1)) -> Response:
    user = require_user(request, db)
    rows, total = order_service.list_orders(db, user, page, ORDER_HISTORY_PAGE_SIZE)
    return render(
        request,
        "orders.html",
        user,
        orders=rows,
        page=page,
        pages=page_count(total, ORDER_HISTORY_PAGE_SIZE),
        total=total,
    )


@router.get("/orders/{order_id}", response_class=HTMLResponse)
def order_detail(request: Request, order_id: uuid.UUID, db: DbDep, placed: int = 0) -> Response:
    user = require_user(request, db)
    try:
        order = order_service.get_order(db, user, order_id)
    except AppError:
        return render(request, "not_found.html", user, status_code=404, what="Order")
    return render(request, "order_detail.html", user, order=order, placed=bool(placed))


@router.post("/orders/{order_id}/cancel", response_class=HTMLResponse)
def cancel_order(
    request: Request, order_id: uuid.UUID, db: DbDep, csrf_token: Annotated[str, Form()] = ""
) -> Response:
    user = require_user(request, db)
    try:
        check_csrf(request, csrf_token)
        order = order_service.cancel_order(db, user, order_id)
    except AppError as exc:
        try:
            order = order_service.get_order(db, user, order_id)
        except AppError:
            return render(request, "not_found.html", user, status_code=404, what="Order")
        return render(
            request,
            "order_detail.html",
            user,
            status_code=exc.status_code,
            order=order,
            error=exc.message,
        )
    return render(request, "order_detail.html", user, order=order, cancelled=True)
