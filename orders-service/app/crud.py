from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas


def create_order(
    db: Session,
    data: schemas.OrderCreate,
) -> models.Order:
    """Create a pending order and persist it to the database."""
    order = models.Order(
        **data.model_dump(),
        predicted_price=None,
        status="pending",
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    return order


def get_order(db: Session, oid: int) -> models.Order | None:
    """Retrieve an order by its ID."""
    return db.get(models.Order, oid)


def list_orders(
    db: Session,
    limit: int = 20,
    offset: int = 0,
) -> list[models.Order]:
    """Return orders sorted by ID in descending order."""
    return list(
        db.scalars(
            select(models.Order)
            .order_by(models.Order.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def update_order(
    db: Session,
    order: models.Order,
    data: schemas.OrderUpdate,
    reset_prediction: bool = False,
) -> models.Order:
    """Update the provided fields of an existing order.

    Property changes invalidate the old forecast and return the order to
    the pending state while its replacement forecast is calculated.
    """
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(order, key, value)

    if reset_prediction:
        order.predicted_price = None
        order.status = "pending"

    db.commit()
    db.refresh(order)

    return order


def complete_order_prediction(
    db: Session,
    order_id: int,
    predicted_price: float | None,
    model_version: str | None = None,
) -> bool:
    """Persist a forecast result without creating or recreating an order."""
    order = get_order(db, order_id)
    if order is None:
        return False

    order.predicted_price = predicted_price
    order.status = "priced" if predicted_price is not None else "failed"
    order.model_version = model_version if predicted_price is not None else None
    db.commit()
    return True


def delete_order(db: Session, order: models.Order) -> None:
    """Delete an existing order from the database."""
    db.delete(order)
    db.commit()
