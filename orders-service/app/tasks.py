import logging

import httpx
from sqlalchemy.exc import SQLAlchemyError

from . import crud
from .celery_app import celery_app
from .database import SessionLocal
from .forecast_client import (
    forecast_error_code,
    request_prediction,
)

logger = logging.getLogger("orders-worker")

PROPERTY_FIELDS = {
    "gr_liv_area",
    "total_bsmt_sf",
    "garage_area",
    "year_built",
    "overall_qual",
    "ms_zoning",
}


@celery_app.task(name="app.tasks.predict_order")
def predict_order(order_id: int) -> None:
    """Calculate a forecast in the worker and persist it on the existing order."""
    with SessionLocal() as db:
        try:
            order = crud.get_order(db, order_id)
            if order is None:
                logger.info(
                    "order forecast order_id=%s result=skipped_missing",
                    order_id,
                )
                return

            payload = {
                field: getattr(order, field)
                for field in PROPERTY_FIELDS
            }
            try:
                price, model_version = request_prediction(payload)
            except (
                httpx.HTTPError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                updated = crud.complete_order_prediction(
                    db,
                    order_id,
                    None,
                )
                result = "failed" if updated else "skipped_missing"
                logger.warning(
                    "order forecast order_id=%s result=%s error=%s",
                    order_id,
                    result,
                    forecast_error_code(exc),
                )
                return

            updated = crud.complete_order_prediction(
                db,
                order_id,
                price,
                model_version,
            )
            result = "priced" if updated else "skipped_missing"
            logger.info(
                "order forecast order_id=%s result=%s model_version=%s",
                order_id,
                result,
                model_version,
            )
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "order forecast order_id=%s result=database_error",
                order_id,
            )
            raise
