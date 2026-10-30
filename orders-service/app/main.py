import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)
from kombu.exceptions import OperationalError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import auth, crud, models, schemas
from .database import Base, engine, get_db
from .forecast_client import (
    FORECAST_TIMEOUT,
    FORECAST_URL,
    forecast_error_code,
)
from .tasks import predict_order

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("orders-api")

BATCH_MAX_ITEMS = int(os.getenv("BATCH_MAX_ITEMS", "50"))
if BATCH_MAX_ITEMS < 1:
    raise RuntimeError("BATCH_MAX_ITEMS must be a positive integer.")

# create_all handles fresh databases; the SQL migration updates existing tables.
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create and close the shared HTTP client used by batch requests."""
    async with httpx.AsyncClient(timeout=FORECAST_TIMEOUT) as client:
        app.state.forecast_client = client
        yield


app = FastAPI(
    title="Orders API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(auth.router)


async def _request_batch_prediction(
    client: httpx.AsyncClient,
    order_id: int,
    index: int,
    payload: dict[str, object],
) -> tuple[float | None, str | None, str | None]:
    try:
        response = await client.post(
            f"{FORECAST_URL}/predict",
            json=payload,
            timeout=FORECAST_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        price = float(body["predicted_price"])
        model_version = str(body["model_version"])
        return price, model_version, None
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        error = forecast_error_code(exc)
        logger.warning(
            "batch forecast index=%s order_id=%s result=failed error=%s",
            index,
            order_id,
            error,
        )
        return None, None, error


def _enqueue_prediction(order_id: int) -> None:
    try:
        predict_order.delay(order_id)
    except OperationalError as exc:
        logger.exception(
            "order forecast order_id=%s result=enqueue_failed",
            order_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The prediction queue is unavailable; "
                "the order remains pending."
            ),
        ) from exc



@app.get("/health")
def health() -> dict[str, str]:
    """Return the health status of the Orders API."""
    return {"status": "ok"}


@app.post(
    "/orders",
    response_model=schemas.OrderRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(auth.get_current_user)],
)
def create_order(
    data: schemas.OrderCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> models.Order:
    """Persist an order and schedule its forecast after returning 202."""
    order = crud.create_order(db, data)
    response.headers["Location"] = str(
        request.url_for("get_order", oid=order.id)
    )
    _enqueue_prediction(order.id)
    return order


@app.post(
    "/orders/batch",
    response_model=schemas.BatchOrderResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(auth.get_current_user)],
)
async def create_orders_batch(
    items: list[schemas.OrderCreate],
    request: Request,
    db: Session = Depends(get_db),
) -> schemas.BatchOrderResponse:
    """Create orders and concurrently request their forecasts."""
    if not items:
        raise HTTPException(
            status_code=422,
            detail="The batch must contain at least one order.",
        )
    if len(items) > BATCH_MAX_ITEMS:
        raise HTTPException(
            status_code=422,
            detail=f"Batch cannot contain more than {BATCH_MAX_ITEMS} orders.",
        )

    orders = [crud.create_order(db, item) for item in items]
    db.close()

    client: httpx.AsyncClient = request.app.state.forecast_client
    forecasts = await asyncio.gather(
        *(
            _request_batch_prediction(
                client,
                order.id,
                index,
                items[index].model_dump(exclude={"client_name"}),
            )
            for index, order in enumerate(orders)
        )
    )

    results: list[schemas.BatchOrderResult] = []
    for index, (order, (price, model_version, error)) in enumerate(
        zip(orders, forecasts, strict=True)
    ):
        try:
            updated = crud.complete_order_prediction(
                db,
                order.id,
                price,
                model_version,
            )
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "batch order index=%s order_id=%s result=database_error",
                index,
                order.id,
            )
            raise

        if not updated:
            results.append(
                schemas.BatchOrderResult(
                    index=index,
                    order_id=order.id,
                    status="failed",
                    model_version=None,
                    error="OrderNotFound",
                )
            )
        elif error is not None:
            results.append(
                schemas.BatchOrderResult(
                    index=index,
                    order_id=order.id,
                    status="failed",
                    model_version=None,
                    error=error,
                )
            )
        else:
            results.append(
                schemas.BatchOrderResult(
                    index=index,
                    order_id=order.id,
                    status="priced",
                    predicted_price=price,
                    model_version=model_version,
                )
            )

    return schemas.BatchOrderResponse(
        total=len(results),
        results=results,
    )


@app.get(
    "/orders",
    response_model=list[schemas.OrderRead],
    dependencies=[Depends(auth.get_current_user)],
)
def list_orders(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Return a paginated list of orders."""
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 100.",
        )

    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Offset must be non-negative.",
        )

    return crud.list_orders(
        db,
        limit,
        offset,
    )


@app.get(
    "/orders/{oid}",
    response_model=schemas.OrderRead,
    dependencies=[Depends(auth.get_current_user)],
)
def get_order(
    oid: int,
    db: Session = Depends(get_db),
):
    """Return a single order by ID."""
    order = crud.get_order(db, oid)

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found.",
        )

    return order


PROPERTY_FIELDS = {
    "gr_liv_area",
    "total_bsmt_sf",
    "garage_area",
    "year_built",
    "overall_qual",
    "ms_zoning",
}


@app.patch(
    "/orders/{oid}",
    response_model=schemas.OrderRead,
    dependencies=[Depends(auth.get_current_user)],
)
def update_order(
    oid: int,
    data: schemas.OrderUpdate,
    response: Response,
    db: Session = Depends(get_db),
) -> models.Order:
    """Update an order and schedule a new forecast when features change."""
    order = crud.get_order(db, oid)

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found.",
        )

    update_data = data.model_dump(exclude_unset=True)
    property_changed = bool(PROPERTY_FIELDS & update_data.keys())

    updated_order = crud.update_order(
        db,
        order,
        data,
        property_changed,
    )
    if property_changed:
        response.status_code = status.HTTP_202_ACCEPTED
        _enqueue_prediction(updated_order.id)

    return updated_order


@app.delete(
    "/orders/{oid}",
    status_code=204,
    dependencies=[Depends(auth.get_current_user)],
)
def delete_order(
    oid: int,
    db: Session = Depends(get_db),
) -> None:
    """Delete an existing order."""
    order = crud.get_order(db, oid)

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found.",
        )

    crud.delete_order(db, order)
