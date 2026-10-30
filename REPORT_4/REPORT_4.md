# Laboratory Work 4 Report

## Environment

- Date shown in the verification logs: 30.10.2026
- Project: House Price Forecast & Orders API
- Operating system: Windows
- Runtime: Docker Compose
- Python: 3.13
- MLflow: 3.1.0
- Dataset: Ames Housing (`training_service/data/ames_train.csv`)
- Evidence: capture the screenshots listed at the end of this report; no Lab 4
  screenshots have been added to this folder yet

## Objectives

1. Move model training and experiment tracking out of the serving image.
2. Track Ridge baseline and tuned XGBoost runs in MLflow, and register model
   versions under aliases.
3. Load the production alias in Forecast API and persist the exact model
   version used for each order forecast.
4. Verify training artifacts, model promotion and rollback, API behavior, and
   secret and network configuration.

## Implementation summary

The Compose stack now includes PostgreSQL, an MLflow 3.1.0 tracking server,
Redis, Orders API, Forecast API, and a separate Celery worker. The one-off
trainer is available through the `train` profile and does not start during a
normal `docker compose up`. The MLflow backend uses the separate `mlflow`
database in the existing PostgreSQL server. The database password is mounted
as a Docker secret; only MLflow mounts the `mlartifacts` volume.

Training code and the CSV are in `training_service/`; the Forecast API image
does not contain either. The trainer fits a Ridge baseline and an XGBoost
pipeline using the same fixed train/hold-out split. The XGBoost target is
transformed with `log1p`/`expm1`, and the numeric feature schema is normalized
to floating point so API requests with decimal values satisfy the model
signature. Optuna uses a seeded TPE sampler, 5-fold cross-validation, and 20
nested trials.

The successful run registered Ridge as model version 3 with alias `baseline`
and XGBoost as version 4 with alias `prod`. Forecast API resolves its alias at
startup, loads the model and the corresponding `data_stats.json` artifact, and
fails startup if the alias cannot be resolved. Its `/health` response reports
the loaded version; `/model/data-stats` serves the statistics from that model's
MLflow run.

Single-order forecasts now use a Celery task queue backed by internal Redis.
The worker updates the existing order row with the prediction, status, and
model version. Orders table migration `002_add_model_version.sql` adds the
version column to an existing database. Batch prediction remains concurrent.

## Training results

The dataset contains **1,460 rows**. SHA-256:

`1e18addf81e5e4d347cc17ee6075bbe4a42b7fa26b9e5b063e8f692a5f929d41`

The hold-out split contains 292 rows; 1,168 rows were used for training.
Both models use `random_state=42` and the same 80/20 split.

| Model | Registry version / alias | Hold-out R² | Hold-out MAE (USD) | Hold-out RMSE (USD) | Hold-out MAPE |
|---|---|---:|---:|---:|---:|
| Ridge baseline | 3 / `baseline` | 0.799449 | 24,275.60 | 39,221.03 | 14.411378% |
| XGBoost, Optuna-selected | 4 / `prod` | 0.876482 | 19,153.46 | 30,780.29 | 11.042576% |

The XGBoost parent run contains **20 nested trial runs**, each logging `cv_r2`.
The best trial's mean 5-fold CV R² was **0.815573**. The production run contains
`data_stats.json`, `reference_data.parquet`, and `target_distributions.png`.
The target skewness changed from **1.882876** before `log1p` to **0.121347**
after it.

## Acceptance-test results

| No. | Scenario | Observed result | Status |
|---:|---|---|---|
| 1 | Validate Compose configuration and secrets | `docker compose config -q` passed; resolved config contained neither secret value. | Pass |
| 2 | Normal Compose startup | PostgreSQL, MLflow, Redis, Forecast API, Orders API, and worker were running; the `trainer` service was not running. | Pass |
| 3 | Isolate training assets | Trainer image contained the CSV; Forecast API image contained neither the CSV nor training modules. | Pass |
| 4 | Run baseline and XGBoost training | Both models registered; baseline alias resolved to version 3 and production alias to version 4. | Pass |
| 5 | Verify Optuna and artifacts | 20 nested trials had `cv_r2`; production run included statistics, reference Parquet, and distribution figure. | Pass |
| 6 | Check Forecast API and statistics | `/health` reported version 4; `/model/data-stats` returned 1,460 rows and target skewness values. | Pass |
| 7 | Create and retrieve an order | Authenticated POST returned `202`, `pending`, null prediction, and `Location`; GET returned `priced`, a numeric prediction, and model version 4. | Pass |
| 8 | PATCH property features | Feature PATCH returned `202`/`pending`; the worker repriced the same order with version 4. | Pass |
| 9 | PATCH client data only | Client-name PATCH returned `200`; prediction and model version remained unchanged. | Pass |
| 10 | Batch forecasts | A two-item batch returned results for both items, each `priced` with model version 4. | Pass |
| 11 | Authentication | An order request without a bearer token returned `401`. | Pass |
| 12 | Alias rollback without rebuilding | `prod` was moved to Ridge version 3; after restarting Forecast API, health, statistics, and prediction all worked on version 3. Alias was restored to version 4 and health reported version 4. | Pass |
| 13 | Missing alias | A one-off Forecast API container configured with an unknown alias exited during startup with an explicit error. The production service and alias were unchanged. | Pass |
| 14 | Internal service ports | Forecast API, Redis, and PostgreSQL had no published host ports; MLflow UI was bound to `127.0.0.1`. | Pass |
| 15 | Environment configuration | `MODEL_VERSION` was removed; model name and alias are configured. No database or JWT secret was placed in `.env`. | Pass |

Test orders and temporary test users were deleted after the checks. The
PostgreSQL volume was preserved. The production alias is currently restored to
version 4.

## Screenshot evidence checklist

Save the screenshots below in this folder. Never include a bearer token,
password, secret-file contents, or an unredacted authorization header.

1. `1.png` — `docker compose ps`: all six long-running services, PostgreSQL
   healthy, and no trainer container.
2. `2.png` — MLflow experiment page showing the Ridge baseline, XGBoost final
   run, and the 20 nested Optuna trial runs.
3. `3.png` — MLflow run metrics table for baseline and final XGBoost, with
   R², MAE, RMSE, and MAPE visible.
4. `4.png` — MLflow Model Registry showing `baseline` → version 3 and `prod` →
   version 4.
5. `5.png` — Terminal output for the trainer run, including dataset digest,
   final trial count, and final metrics.
6. `6.png` — Internal Forecast API health and data statistics, captured from
   `docker compose exec orders-api ...`; include loaded version 4 and 1,460
   rows.
7. `7.png` — Swagger `POST /orders` response showing `202`, `pending`, null
   prediction, and `Location`. Keep the token out of the screenshot.
8. `8.png` — Swagger `GET /orders/{oid}` after the worker finishes, showing
   `priced`, numeric prediction, and `model_version: "4"`.
9. `9.png` — Property PATCH returning `202`/`pending`, followed by the GET
   response after repricing. A client-name-only PATCH can be shown alongside
   the unchanged prediction.
10. `10.png` — Batch response with all items priced and model version 4, plus
    an unauthenticated order request returning `401`.
11. `11.png` — Rollback timeline: set alias `prod` to version 3, restart
    Forecast API without rebuilding, show health version 3, restore version 4,
    and show health version 4.
12. `12.png` — Unknown-alias startup failure and sanitized secret/config
    verification. Do not display `.env` secret values or secret files.

For the rollback screenshot, use the MLflow UI or the `MlflowClient` command
documented in `README.md`. Immediately restore alias `prod` to version 4 after
the screenshot.

## Limitations

The optional Evidently drift-monitoring job was not implemented. The CSV is
ignored by the repository's existing `*.csv` rule, so it must be present at
`training_service/data/ames_train.csv` before building or running the trainer.
The MLflow UI is operator-only and has no authentication; it is bound to
localhost by default and must not be exposed publicly without additional
access controls.
