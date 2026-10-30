import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mlflow
import mlflow.data
import mlflow.sklearn
import numpy as np
import optuna
import pandas as pd
from mlflow import MlflowClient
from mlflow.models import infer_signature
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    r2_score,
    root_mean_squared_error,
)
from sklearn.model_selection import (
    KFold,
    cross_val_score,
    train_test_split,
)

from .model import (
    CATEGORICAL,
    FEATURES,
    NUMERIC,
    SEED,
    TARGET,
    build_ridge_model,
    build_xgboost_model,
    load_training_data,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("trainer")

DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "ames_train.csv"
MODEL_NAME = os.getenv("MODEL_NAME", "house-price")
EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "house-price")
TRIAL_COUNT = int(os.getenv("OPTUNA_TRIALS", "20"))


def evaluate(model: Any, features: pd.DataFrame, target: pd.Series) -> dict[str, float]:
    predictions = model.predict(features)
    return {
        "holdout_r2": float(r2_score(target, predictions)),
        "holdout_mae": float(mean_absolute_error(target, predictions)),
        "holdout_rmse": float(root_mean_squared_error(target, predictions)),
        "holdout_mape": float(
            mean_absolute_percentage_error(target, predictions) * 100
        ),
    }


def make_dataset_input(
    training_features: pd.DataFrame,
    training_target: pd.Series,
):
    training_data = training_features.copy()
    training_data[TARGET] = training_target
    return mlflow.data.from_pandas(
        training_data,
        source=DATASET_PATH.resolve().as_uri(),
        targets=TARGET,
        name="ames-housing",
    )


def dataset_digest() -> str:
    digest = hashlib.sha256()
    with DATASET_PATH.open("rb") as dataset_file:
        for chunk in iter(lambda: dataset_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def log_data_statistics(data: pd.DataFrame, training_features: pd.DataFrame) -> None:
    target = data[TARGET]
    target_log = np.log1p(target)
    stats: dict[str, Any] = {
        "row_count": int(len(data)),
        "column_count": int(len(data.columns)),
        "missing_fraction": {
            column: float(value)
            for column, value in data.isna().mean().items()
        },
        "numeric_features": {
            column: {
                name: float(value)
                for name, value in data[column].describe().items()
            }
            for column in NUMERIC
        },
        "categorical_features": {
            column: {
                str(name): int(value)
                for name, value in data[column]
                .fillna("<missing>")
                .value_counts()
                .items()
            }
            for column in CATEGORICAL
        },
        "target": {
            "mean": float(target.mean()),
            "standard_deviation": float(target.std()),
            "skewness_before_log1p": float(target.skew()),
            "skewness_after_log1p": float(target_log.skew()),
        },
        "feature_columns": FEATURES,
    }

    mlflow.log_dict(stats, "data_stats.json")
    mlflow.log_metric("row_count", len(data))
    mlflow.log_metric("target_skewness_before_log1p", target.skew())
    mlflow.log_metric("target_skewness_after_log1p", target_log.skew())
    mlflow.log_param("dataset_sha256", dataset_digest())

    figure, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].hist(target, bins=40)
    axes[0].set_title("SalePrice before log1p")
    axes[0].set_xlabel("SalePrice (USD)")
    axes[1].hist(target_log, bins=40)
    axes[1].set_title("SalePrice after log1p")
    axes[1].set_xlabel("log1p(SalePrice)")
    figure.tight_layout()
    mlflow.log_figure(figure, "target_distributions.png")
    plt.close(figure)

    with tempfile.TemporaryDirectory() as temp_dir:
        reference_path = Path(temp_dir) / "reference_data.parquet"
        training_features.to_parquet(reference_path, index=False)
        mlflow.log_artifact(reference_path)


def register_model(run_id: str, alias: str | None = None) -> str:
    model_uri = f"runs:/{run_id}/model"
    registered = mlflow.register_model(model_uri, MODEL_NAME)
    client = MlflowClient()
    client.get_model_version(
        name=MODEL_NAME,
        version=registered.version,
    )
    if alias is not None:
        client.set_registered_model_alias(
            MODEL_NAME,
            alias,
            registered.version,
        )
    return str(registered.version)


def log_baseline(
    data: pd.DataFrame,
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
) -> None:
    model = build_ridge_model()
    model.fit(x_train, y_train)
    metrics = evaluate(model, x_test, y_test)
    dataset = make_dataset_input(x_train, y_train)

    with mlflow.start_run(run_name="ridge-baseline") as run:
        mlflow.log_param("model_family", "Ridge")
        mlflow.log_param("random_state", SEED)
        mlflow.log_param("test_size", 0.2)
        mlflow.log_param("dataset_sha256", dataset_digest())
        mlflow.log_metrics(metrics)
        mlflow.log_input(dataset, context="train")
        log_data_statistics(data, x_train)
        signature = infer_signature(
            x_train,
            model.predict(x_train),
        )
        mlflow.sklearn.log_model(
            model,
            name="model",
            signature=signature,
            input_example=x_train.head(3),
        )
        version = register_model(run.info.run_id, alias="baseline")

    logger.info(
        "baseline run_id=%s version=%s metrics=%s",
        run.info.run_id,
        version,
        json.dumps(metrics, sort_keys=True),
    )


def optimize_xgboost(
    data: pd.DataFrame,
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
) -> None:
    dataset = make_dataset_input(x_train, y_train)
    cv = KFold(n_splits=5, shuffle=True, random_state=SEED)
    sampler = optuna.samplers.TPESampler(seed=SEED)

    with mlflow.start_run(run_name="xgboost-optuna-search"):
        mlflow.log_param("dataset_sha256", dataset_digest())
        mlflow.log_param("optuna_trials", TRIAL_COUNT)
        mlflow.log_param("cv_folds", 5)
        mlflow.log_input(dataset, context="train")

        def objective(trial: optuna.Trial) -> float:
            params: dict[str, int | float] = {
                "n_estimators": trial.suggest_int(
                    "n_estimators",
                    200,
                    1000,
                ),
                "max_depth": trial.suggest_int("max_depth", 2, 8),
                "learning_rate": trial.suggest_float(
                    "learning_rate",
                    0.01,
                    0.3,
                    log=True,
                ),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float(
                    "colsample_bytree",
                    0.6,
                    1.0,
                ),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.0, 10.0),
            }
            with mlflow.start_run(
                run_name=f"xgboost-trial-{trial.number:02d}",
                nested=True,
            ):
                mlflow.log_params(params)
                scores = cross_val_score(
                    build_xgboost_model(params),
                    x_train,
                    y_train,
                    cv=cv,
                    scoring="r2",
                    n_jobs=1,
                )
                cv_r2 = float(scores.mean())
                mlflow.log_metric("cv_r2", cv_r2)
                mlflow.log_metric("cv_r2_std", float(scores.std()))
                return cv_r2

        study = optuna.create_study(
            direction="maximize",
            sampler=sampler,
        )
        study.optimize(objective, n_trials=TRIAL_COUNT)
        mlflow.log_metric("best_cv_r2", study.best_value)
        mlflow.log_params(
            {f"best_{key}": value for key, value in study.best_params.items()}
        )

    final_model = build_xgboost_model(study.best_params)
    final_model.fit(x_train, y_train)
    metrics = evaluate(final_model, x_test, y_test)
    dataset = make_dataset_input(x_train, y_train)

    with mlflow.start_run(run_name="xgboost-final") as final_run:
        mlflow.log_params(study.best_params)
        mlflow.log_param("model_family", "XGBoost")
        mlflow.log_param("random_state", SEED)
        mlflow.log_param("test_size", 0.2)
        mlflow.log_param("dataset_sha256", dataset_digest())
        mlflow.log_metrics(metrics)
        mlflow.log_input(dataset, context="train")
        log_data_statistics(data, x_train)
        signature = infer_signature(
            x_train,
            final_model.predict(x_train),
        )
        mlflow.sklearn.log_model(
            final_model,
            name="model",
            signature=signature,
            input_example=x_train.head(3),
        )
        version = register_model(final_run.info.run_id, alias="prod")

    logger.info(
        "final run_id=%s version=%s metrics=%s best_params=%s",
        final_run.info.run_id,
        version,
        json.dumps(metrics, sort_keys=True),
        json.dumps(study.best_params, sort_keys=True),
    )


def main() -> None:
    if TRIAL_COUNT < 20:
        raise ValueError("OPTUNA_TRIALS must be at least 20.")

    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    mlflow.set_experiment(EXPERIMENT_NAME)
    data = load_training_data(str(DATASET_PATH))
    train_data, test_data = train_test_split(
        data,
        test_size=0.2,
        random_state=SEED,
    )
    x_train = train_data[FEATURES]
    x_test = test_data[FEATURES]
    y_train = train_data[TARGET]
    y_test = test_data[TARGET]

    logger.info(
        "dataset rows=%s sha256=%s train_rows=%s test_rows=%s",
        len(data),
        dataset_digest(),
        len(x_train),
        len(x_test),
    )
    log_baseline(data, x_train, x_test, y_train, y_test)
    optimize_xgboost(data, x_train, x_test, y_train, y_test)


if __name__ == "__main__":
    main()
