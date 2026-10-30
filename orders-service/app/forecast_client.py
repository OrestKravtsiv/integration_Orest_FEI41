import os

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

FORECAST_URL = os.getenv("FORECAST_URL", "http://forecast-api:8001")
FORECAST_TIMEOUT = float(os.getenv("FORECAST_TIMEOUT", "3.0"))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.3, max=2),
    retry=retry_if_exception_type(
        (httpx.ConnectError, httpx.TimeoutException)
    ),
    reraise=True,
)
def request_prediction(payload: dict[str, object]) -> tuple[float, str]:
    """Request a price and the exact registered model version that produced it."""
    with httpx.Client(timeout=FORECAST_TIMEOUT) as client:
        response = client.post(f"{FORECAST_URL}/predict", json=payload)
        response.raise_for_status()
        body = response.json()
        return float(body["predicted_price"]), str(body["model_version"])


def forecast_error_code(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "ForecastTimeout"
    if isinstance(exc, httpx.ConnectError):
        return "ForecastUnavailable"
    if isinstance(exc, httpx.HTTPStatusError):
        return "ForecastHTTPError"
    if isinstance(exc, httpx.HTTPError):
        return "ForecastRequestError"
    return "ForecastInvalidResponse"
