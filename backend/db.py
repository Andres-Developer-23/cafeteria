import os

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, create_engine, func
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cafeteria.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    description = Column(String(300), default="")
    category = Column(String(40), nullable=False)  # bebidas | alimentos | postres
    price = Column(Float, nullable=False)
    emoji = Column(String(10), default="☕")
    available = Column(Boolean, default=True)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    customer_name = Column(String(120), nullable=False)
    status = Column(String(20), default="pending")  # pending|paid|preparing|ready|completed|cancelled
    total = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    items = relationship("OrderItem", back_populates="order")
    payment = relationship("Payment", back_populates="order", uselist=False)


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    name = Column(String(120), nullable=False)  # snapshot del nombre al momento de pedir
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    order = relationship("Order", back_populates="items")


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String(20), default="card")
    card_last4 = Column(String(4), default="")
    status = Column(String(20), nullable=False)  # approved | rejected
    transaction_id = Column(String(64), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    order = relationship("Order", back_populates="payment")


MENU_SEED = [
    # bebidas
    ("Espresso", "Café espresso puro, 60 ml", "bebidas", 35.0, "☕"),
    ("Americano", "Espresso con agua caliente", "bebidas", 42.0, "☕"),
    ("Cappuccino", "Espresso, leche vaporizada y espuma", "bebidas", 52.0, "🍮"),
    ("Latte", "Espresso con mucha leche vaporizada", "bebidas", 55.0, "🥛"),
    ("Mocha", "Espresso, chocolate y leche", "bebidas", 60.0, "🍫"),
    ("Té chai", "Té negro con especias y leche", "bebidas", 48.0, "🍵"),
    ("Jugo de naranja natural", "Naranjas exprimidas al momento", "bebidas", 45.0, "🍊"),
    ("Agua natural", "Botella 500 ml", "bebidas", 25.0, "💧"),
    # alimentos
    ("Croissant", "Hojaldre mantequillado recién horneado", "alimentos", 38.0, "🥐"),
    ("Pan de ajo", "Con ajo, perejil y mantequilla", "alimentos", 42.0, "🥖"),
    ("Sándwich de jamón y queso", "Pan tostado, jamón, queso y vegetales", "alimentos", 75.0, "🥪"),
    ("Bagel con queso crema", "Bagel tostado con queso crema", "alimentos", 58.0, "🥯"),
    ("Ensalada del día", "Mixta con pollo a la plancha", "alimentos", 95.0, "🥗"),
    # postres
    ("Cheesecake", "Con frutos rojos", "postres", 68.0, "🍰"),
    ("Brownie", "Con nuez y chocolate", "postres", 52.0, "🍫"),
    ("Galleta de chocolate", "Hecha en casa", "postres", 28.0, "🍪"),
    ("Muffin de arándanos", "Bizcocho con arándanos frescos", "postres", 45.0, "🧁"),
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as s:
        if s.query(Product).count() == 0:
            for name, desc, cat, price, emoji in MENU_SEED:
                s.add(Product(name=name, description=desc, category=cat, price=price, emoji=emoji))
            s.commit()
