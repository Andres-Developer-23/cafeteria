"""Pruebas del flujo de pedidos y pagos. Ejecutar: python -m pytest test_api.py -q"""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_menu_has_products():
    r = client.get("/api/menu")
    assert r.status_code == 200
    menu = r.json()
    assert len(menu) >= 10
    assert all({"id", "name", "price", "category"} <= set(p) for p in menu)


def _create_order(total_items_qty=1):
    menu = client.get("/api/menu").json()
    pid = menu[0]["id"]
    r = client.post("/api/orders", json={"customer_name": "Ana Prueba", "items": [{"product_id": pid, "quantity": total_items_qty}]})
    assert r.status_code == 201
    body = r.json()
    expected = round(menu[0]["price"] * total_items_qty, 2)
    assert body["total"] == expected
    return body


def test_order_then_pay_approved():
    order = _create_order(2)
    r = client.post("/api/payments", json={
        "order_id": order["order_id"],
        "card_number": "4242424242424242",  # tarjeta Visa de prueba, pasa Luhn
        "exp_month": 12, "exp_year": 2030, "cvc": "123", "holder_name": "Ana Prueba",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["payment_status"] == "approved"
    assert body["order_status"] == "paid"
    assert body["transaction_id"].startswith("txn_")


def test_pay_declined_card():
    order = _create_order()
    r = client.post("/api/payments", json={
        "order_id": order["order_id"],
        "card_number": "4000000000000002",
        "exp_month": 12, "exp_year": 2030, "cvc": "123", "holder_name": "Ana Prueba",
    })
    body = r.json()
    assert body["payment_status"] == "rejected"
    assert body["order_status"] == "pending"


def test_pay_invalid_card_number():
    order = _create_order()
    r = client.post("/api/payments", json={
        "order_id": order["order_id"],
        "card_number": "1234567812345678",  # no pasa Luhn
        "exp_month": 12, "exp_year": 2030, "cvc": "123", "holder_name": "Ana Prueba",
    })
    assert r.json()["payment_status"] == "rejected"


def test_double_pay_rejected():
    order = _create_order()
    payload = {"order_id": order["order_id"], "card_number": "4242424242424242",
               "exp_month": 12, "exp_year": 2030, "cvc": "123", "holder_name": "Ana Prueba"}
    assert client.post("/api/payments", json=payload).json()["payment_status"] == "approved"
    r = client.post("/api/payments", json=payload)
    assert r.status_code == 400


def test_admin_requires_token():
    assert client.get("/api/orders").status_code == 401
    assert client.get("/api/orders", headers={"X-Admin-Token": "dev-admin-token"}).status_code == 200


def test_status_transitions():
    order = _create_order()
    hid = {"X-Admin-Token": "dev-admin-token"}
    # saltar a 'ready' sin pasar por 'preparing' debe fallar
    r = client.patch(f"/api/orders/{order['order_id']}/status", json={"status": "ready"}, headers=hid)
    assert r.status_code == 400
    # flujo válido paid -> preparing -> ready -> completed
    client.post("/api/payments", json={"order_id": order["order_id"], "card_number": "4242424242424242",
                                       "exp_month": 12, "exp_year": 2030, "cvc": "123", "holder_name": "Ana"})
    for st in ("preparing", "ready", "completed"):
        r = client.patch(f"/api/orders/{order['order_id']}/status", json={"status": st}, headers=hid)
        assert r.status_code == 200 and r.json()["status"] == st
