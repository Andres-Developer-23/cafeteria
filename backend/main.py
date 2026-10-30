import os
import uuid
from decimal import ROUND_HALF_UP, Decimal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import Order, OrderItem, Payment, Product, SessionLocal, init_db

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "dev-admin-token")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

app = FastAPI(title="Café Aroma API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_STATUSES = {"pending", "paid", "preparing", "ready", "completed", "cancelled"}
NEXT_STATUSES = {
    "paid": {"preparing", "cancelled"},
    "preparing": {"ready", "cancelled"},
    "ready": {"completed"},
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_admin(x_admin_token: str = Header(default="")):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Token de administrador inválido")


# ---------- esquemas ----------

class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=50)

class OrderIn(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    items: list[OrderItemIn] = Field(min_length=1, max_length=30)

class PaymentIn(BaseModel):
    order_id: int
    card_number: str = Field(min_length=12, max_length=23)
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=2020, le=2100)
    cvc: str = Field(min_length=3, max_length=4)
    holder_name: str = Field(min_length=2, max_length=120)

class StatusIn(BaseModel):
    status: str


# ---------- pasarela de pago (sandbox) ----------

def luhn_valid(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 12:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# Tarjeta de prueba que siempre se rechaza, para probar el flujo de error.
DECLINE_CARD = "4000000000000002"


def charge_card(number: str, amount: float, exp_month: int, exp_year: int, cvc: str) -> dict:
    """Pasarela en modo sandbox. Para producción, sustituir por Stripe u otra pasarela real."""
    digits = "".join(c for c in number if c.isdigit())
    if not luhn_valid(digits):
        return {"status": "rejected", "reason": "Número de tarjeta inválido"}
    if len(cvc) < 3 or not cvc.isdigit():
        return {"status": "rejected", "reason": "CVC inválido"}
    if digits == DECLINE_CARD:
        return {"status": "rejected", "reason": "Tarjeta rechazada por el banco emisor"}
    return {
        "status": "approved",
        "transaction_id": f"txn_{uuid.uuid4().hex[:20]}",
        "last4": digits[-4:],
        "amount": amount,
    }


# ---------- rutas ----------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "cafeteria-api"}


@app.get("/api/menu")
def menu(db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.available.is_(True)).order_by(Product.category, Product.id).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "category": p.category,
            "price": p.price,
            "emoji": p.emoji,
        }
        for p in products
    ]


@app.post("/api/orders", status_code=201)
def create_order(payload: OrderIn, db: Session = Depends(get_db)):
    total = Decimal("0")
    items = []
    for it in payload.items:
        product = db.get(Product, it.product_id)
        if not product or not product.available:
            raise HTTPException(status_code=400, detail=f"Producto {it.product_id} no disponible")
        total += Decimal(str(product.price)) * it.quantity
        items.append(
            OrderItem(
                product_id=product.id,
                name=product.name,
                quantity=it.quantity,
                unit_price=product.price,
            )
        )
    total = float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    order = Order(customer_name=payload.customer_name.strip(), status="pending", total=total, items=items)
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"order_id": order.id, "status": order.status, "total": order.total,
            "items": [{"name": i.name, "quantity": i.quantity, "unit_price": i.unit_price} for i in order.items]}


@app.post("/api/payments")
def pay(payload: PaymentIn, db: Session = Depends(get_db)):
    order = db.get(Order, payload.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if order.status != "pending":
        raise HTTPException(status_code=400, detail=f"El pedido ya fue pagado (estado: {order.status})")

    result = charge_card(payload.card_number, order.total, payload.exp_month, payload.exp_year, payload.cvc)

    payment = Payment(
        order_id=order.id,
        amount=order.total,
        method="card",
        card_last4=result.get("last4", ""),
        status=result["status"],
        transaction_id=result.get("transaction_id", f"rej_{uuid.uuid4().hex[:16]}"),
    )
    db.add(payment)
    if result["status"] == "approved":
        order.status = "paid"
    db.commit()
    db.refresh(order)

    body = {
        "payment_status": result["status"],
        "transaction_id": payment.transaction_id,
        "order_id": order.id,
        "order_status": order.status,
        "amount": order.amount if hasattr(order, "amount") else order.total,
    }
    if result["status"] == "rejected":
        body["reason"] = result.get("reason", "Pago rechazado")
    return body


@app.get("/api/orders")
def list_orders(_: None = Depends(check_admin), db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.created_at.desc(), Order.id.desc()).limit(100).all()
    return [
        {
            "id": o.id,
            "customer_name": o.customer_name,
            "status": o.status,
            "total": o.total,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "items": [{"name": i.name, "quantity": i.quantity, "unit_price": i.unit_price} for i in o.items],
            "payment": (
                {"status": o.payment.status, "card_last4": o.payment.card_last4,
                 "transaction_id": o.payment.transaction_id}
                if o.payment
                else None
            ),
        }
        for o in orders
    ]


@app.patch("/api/orders/{order_id}/status")
def update_status(order_id: int, payload: StatusIn, _: None = Depends(check_admin), db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Estado inválido")
    if payload.status not in NEXT_STATUSES.get(order.status, set()) and payload.status != order.status:
        allowed = ", ".join(sorted(NEXT_STATUSES.get(order.status, set()))) or "ninguno"
        raise HTTPException(status_code=400, detail=f"No se puede pasar de '{order.status}' a '{payload.status}'. Permitidos: {allowed}")
    order.status = payload.status
    db.commit()
    return {"id": order.id, "status": order.status}


# Crea las tablas y siembra el menú la primera vez que arranca (idempotente).
init_db()
