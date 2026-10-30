import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import mlflow
import mlflow.pyfunc
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from mlflow import MlflowClient

from .schemas import PredictRequest, PredictResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("forecast-api")

MODEL_NAME = os.getenv("MODEL_NAME", "house-price")
MODEL_ALIAS = os.getenv("MODEL_ALIAS", "prod")
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    "http://mlflow:5000",
)
NUMERIC_FEATURES = [
    "GrLivArea",
    "TotalBsmtSF",
    "GarageArea",
    "YearBuilt",
    "OverallQual",
]
CATEGORICAL_FEATURES = ["MSZoning"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Resolve the registry alias and load its model and statistics at startup."""
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()
    try:
        model_version = client.get_model_version_by_alias(
            MODEL_NAME,
            MODEL_ALIAS,
        )
        model = mlflow.pyfunc.load_model(
            f"models:/{MODEL_NAME}@{MODEL_ALIAS}"
        )
        stats_path = mlflow.artifacts.download_artifacts(
            run_id=model_version.run_id,
            artifact_path="data_stats.json",
        )
        data_stats = json.loads(
            Path(stats_path).read_text(encoding="utf-8")
        )
    except Exception as exc:
        logger.exception(
            "Failed to resolve model registry alias %s@%s",
            MODEL_NAME,
            MODEL_ALIAS,
        )
        raise RuntimeError(
            f"Could not load registry model {MODEL_NAME}@{MODEL_ALIAS}"
        ) from exc

    app.state.model = model
    app.state.model_version = str(model_version.version)
    app.state.data_stats = data_stats
    logger.info(
        "Loaded model %s@%s version=%s run_id=%s",
        MODEL_NAME,
        MODEL_ALIAS,
        model_version.version,
        model_version.run_id,
    )
    yield
    app.state.model = None
    app.state.data_stats = None


app = FastAPI(
    title="Forecast API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health(request: Request) -> dict[str, str]:
    """Report the model version currently loaded from the registry."""
    return {
        "status": "ok",
        "model_version": request.app.state.model_version,
    }


@app.get("/model/data-stats")
def model_data_stats(request: Request) -> dict[str, object]:
    """Return statistics logged with the model's registry run."""
    return request.app.state.data_stats


@app.post("/predict", response_model=PredictResponse)
def predict(
    req: PredictRequest,
    request: Request,
) -> PredictResponse:
    """Predict a house sale price using the model loaded from the registry."""
    started_at = time.perf_counter()
    features = pd.DataFrame(
        [
            {
                "GrLivArea": req.gr_liv_area,
                "TotalBsmtSF": req.total_bsmt_sf,
                "GarageArea": req.garage_area,
                "YearBuilt": req.year_built,
                "OverallQual": req.overall_qual,
                "MSZoning": req.ms_zoning,
            }
        ],
        columns=NUMERIC_FEATURES + CATEGORICAL_FEATURES,
    )
    features[NUMERIC_FEATURES] = features[NUMERIC_FEATURES].astype("float64")
    prediction = request.app.state.model.predict(features)
    predicted_price = float(prediction[0])
    latency_ms = round(
        (time.perf_counter() - started_at) * 1000,
        2,
    )
    model_version = request.app.state.model_version
    logger.info(
        "predict: %.2f USD model_version=%s (%.2f ms)",
        predicted_price,
        model_version,
        latency_ms,
    )
    return PredictResponse(
        predicted_price=predicted_price,
        model_version=model_version,
        latency_ms=latency_ms,
    )
