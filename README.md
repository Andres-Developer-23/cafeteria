# ☕ Café Aroma — Sistema de Cafetería

Sistema completo de cafetería: menú en línea, carrito, pedidos, pagos con tarjeta y panel de cocina.

## Stack

| Capa | Tecnología | Hosting |
|------|-----------|---------|
| Frontend | Astro (estático, JS vanilla) | Render Static Site |
| Backend API | FastAPI + SQLAlchemy | Render Web Service |
| Base de datos | PostgreSQL | Render Postgres |
| Pagos | Pasarela sandbox integrada (lista para Stripe) | — |

## Funcionalidades

- **Menú** con categorías (bebidas, alimentos, postres), precios y disponibilidad.
- **Carrito** persistente (localStorage) y creación de pedidos con total calculado en el servidor.
- **Pagos con tarjeta**: validación Luhn, expiración, CVC, registro de transacción y rechazo de doble pago.
- **Panel de cocina** (`/admin`): pedidos en vivo con polling, flujo de estados
  `pagado → preparando → listo → entregado` (y cancelación), protegido por token.

### Tarjetas de prueba (modo sandbox)

| Tarjeta | Resultado |
|---------|-----------|
| `4242 4242 4242 4242` | ✅ Aprobado |
| `4000 0000 0000 0002` | ❌ Rechazada |
| cualquier número que no pase Luhn | ❌ Número inválido |

## API

- `GET  /api/health` — estado del servicio
- `GET  /api/menu` — productos disponibles
- `POST /api/orders` — crear pedido `{customer_name, items:[{product_id, quantity}]}`
- `POST /api/payments` — pagar un pedido con tarjeta
- `GET  /api/orders` — listar pedidos (requiere header `X-Admin-Token`)
- `PATCH /api/orders/{id}/status` — avanzar estado del pedido (admin)

## Desarrollo local

```bash
# Backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest
uvicorn main:app --reload          # http://localhost:8000

# Frontend (otra terminal)
cd frontend
npm install
PUBLIC_API_URL=http://localhost:8000/api npm run dev   # http://localhost:4321
```

## Pruebas

```bash
cd backend && python -m pytest test_api.py -q
```

## Producción

| Recurso | URL |
|---------|-----|
| Sitio web (Astro) | https://cafeteria-aroma-web-69a2.onrender.com |
| Panel de cocina | https://cafeteria-aroma-web-69a2.onrender.com/admin |
| API (FastAPI) | https://cafeteria-aroma-api.onrender.com |
| Health check | https://cafeteria-aroma-api.onrender.com/api/health |
| Base de datos | Render Postgres `cafeteria-aroma-db` (oregon) |

El backend (`backend/`) y el frontend (`frontend/`) viven en este mismo monorepo.
Render despliega desde GitHub: el web service usa `backend/` (runtime Python) y el
static site construye `frontend/` con Node. Cada push a `main` redespliega ambos.

Para conectar **Stripe** en producción: reemplaza la función `charge_card()` en
`backend/main.py` por una llamada real a la Stripe API (misma firma).
