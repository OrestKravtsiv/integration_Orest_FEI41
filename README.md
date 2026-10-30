# House Price Forecast & Orders API

A Docker Compose application with an Orders API, an internal Forecast API, a
Celery prediction worker, Redis, PostgreSQL, and an MLflow model registry.
Orders API is the only public application API. Forecast and Redis are internal;
the MLflow UI is bound to localhost for operator access.

## Services and access

| Service | Access |
|---|---|
| Orders API | Host port `${ORDERS_PORT:-8000}` |
| Forecast API | Internal only, `http://forecast-api:8001` |
| PostgreSQL | Internal only, service `postgres:5432` |
| Redis | Internal only, service `redis:6379` |
| MLflow | Internal tracking server; UI at `http://localhost:${MLFLOW_PORT:-5000}` |
| Trainer | Manual, one-off service in the `train` profile |

Public Orders API routes:

| Method | Route | Access |
|---|---|---|
| GET | `/health` | Public |
| POST | `/orders/batch` | Authenticated |
| POST | `/auth/register` | Public |
| POST | `/auth/login` | Public; form-encoded |
| GET | `/auth/me` | Bearer token |
| GET, POST | `/orders` | Bearer token |
| GET, PATCH, DELETE | `/orders/{oid}` | Bearer token |

Missing, invalid, expired, or inactive-user credentials return `401` with
`WWW-Authenticate: Bearer`. Passwords are hashed using Argon2id. JWTs use HS256
and expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30 minutes).

## Requirements

- Docker Engine and Docker Compose
- The training file `training_service/data/ames_train.csv`
- `uv` for local dependency management (optional when using Docker)

The CSV must include `GrLivArea`, `TotalBsmtSF`, `GarageArea`, `YearBuilt`,
`OverallQual`, `MSZoning`, and `SalePrice`.

## Configuration and secrets

Copy `.env.example` to `.env` and set non-secret configuration only.
`MODEL_NAME` and `MODEL_ALIAS` select the
registered model. Orders persist the exact numeric model version returned by
Forecast API; the Forecast API resolves the alias at startup and fails to start
if it cannot resolve or load it.

Do not put database passwords or JWT signing keys in `.env`. The MLflow UI
defaults to loopback only; do not bind it to a public interface without adding
authentication and network controls. Follow
[`secrets/README.md`](secrets/README.md) to provision `secrets/db_password` and
`secrets/jwt_secret_key`. Real secret files are gitignored and mounted read-only
at `/run/secrets/`. The Orders API fails at startup if a required secret is
missing or empty. Secret values are not build arguments, environment variables,
or image contents.

## Start and verify

The first startup against a new PostgreSQL volume creates the `mlflow` database
automatically. If `pgdata` already existed before this lab, start PostgreSQL
and create the additional database once (do not delete the volume):

```powershell
docker compose up -d postgres
docker compose exec postgres psql -U orders -d postgres -c "CREATE DATABASE mlflow;"
```

Train and register the baseline and production models before starting Forecast
API. The trainer is not started by a normal `docker compose up`:

```powershell
docker compose up -d --build postgres mlflow
docker compose build trainer
docker compose run --rm trainer
```

This run logs a Ridge baseline under alias `baseline`, evaluates an XGBoost
model with at least 20 Optuna trials, and publishes the selected XGBoost version
under alias `prod`. Then apply the model-version migration to an existing orders
database and start the application:

```bash
docker compose up -d --build
```

Check status and logs:

```bash
docker compose ps
docker compose logs orders-api
docker compose logs postgres
```

Orders API and Swagger UI:

- `http://localhost:8000/health`
- `http://localhost:8000/docs`

The Forecast API is not exposed on `localhost:8001`. To verify internal
reachability:

```bash
docker compose exec orders-api python -c "import urllib.request; print(urllib.request.urlopen('http://forecast-api:8001/health').read().decode())"
```

`docker compose config` can be used to inspect the resolved Compose setup. Secret
values should not appear there; only secret file references are configured.
The MLflow UI is an operator interface, not an authenticated public endpoint.
Only the MLflow service mounts the `mlartifacts` volume; other services access
models and artifacts through the tracking server.

## Register, log in, and use the API

Register a user. Passwords must be 8–72 bytes after UTF-8 encoding; extra fields
(including privilege-related fields) are rejected.

```powershell
curl.exe -i -X POST http://localhost:8000/auth/register `
  -H "Content-Type: application/json" `
  -d '{"username":"alice","password":"correct-horse"}'
```

These examples use PowerShell line continuations. On Bash, replace each
backtick with `\`.

Log in with an OAuth2-compatible form-encoded request:

```powershell
curl.exe -i -X POST http://localhost:8000/auth/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  --data-urlencode "username=alice" `
  --data-urlencode "password=correct-horse"
```

Copy `access_token` from the response and authorize in Swagger UI, or pass it in
the `Authorization` header:

```powershell
curl.exe http://localhost:8000/auth/me `
  -H "Authorization: Bearer <access_token>"
```

Create an order (the service requests the estimate from the internal Forecast
API):

```powershell
curl.exe -i -X POST http://localhost:8000/orders `
  -H "Authorization: Bearer <access_token>" `
  -H "Content-Type: application/json" `
  -d '{"client_name":"Alice Brown","gr_liv_area":2000,"total_bsmt_sf":1200,"garage_area":550,"year_built":2000,"overall_qual":8,"ms_zoning":"RL"}'
```

`POST /orders` immediately returns `202 Accepted` with status `pending` and a
`Location` header. Poll the returned order URL or use `GET /orders/{oid}` to
read its final `priced` or `failed` status.

`POST /orders/batch` accepts an array of the same order objects and waits for
all concurrent forecasts before returning per-order results. Its maximum size
is controlled by `BATCH_MAX_ITEMS` (default 50). A forecast failure affects
only that item; valid orders are still persisted.

All `/orders` requests require the bearer token. PATCH requests that change a
property feature clear the old prediction, return `202 Accepted`, and schedule
a new forecast. PATCH requests that change only client data do not recalculate
the prediction.

Single-order forecasts are queued in Redis and executed by the separate
`orders-worker` Celery service. Results update the existing order row, including
the model version used. Batch forecasts remain concurrent HTTP requests and
return per-item results.

## Database migration

For a database created before this lab, apply the model-version migration once
before using the updated API:

```powershell
Get-Content .\orders-service\migrations\002_add_model_version.sql |
  docker compose exec -T postgres psql -U orders -d orders
```

If migration `001_add_order_status.sql` has not already been applied to an
older database, apply it before migration 002.

In Swagger UI (`/docs`), use **Authorize**. The OAuth2 token URL is
`/auth/login`.

## Training, promotion, and rollback

The training image contains the dataset and training dependencies; neither is
included in the Forecast API image. Training logs hold-out R², MAE, RMSE, and
MAPE, the dataset digest and statistics, nested Optuna trial runs, model
artifacts, and a reference Parquet dataset to MLflow.

To promote or roll back, change the `prod` alias in MLflow to the chosen
registered model version, then restart Forecast API. No image rebuild is needed:

```powershell
docker compose exec -e MLFLOW_TRACKING_URI=http://localhost:5000 mlflow mlflow models set-alias --name house-price --alias prod --version <VERSION>
docker compose restart forecast-api
docker compose exec orders-api python -c "import urllib.request; print(urllib.request.urlopen('http://forecast-api:8001/health').read().decode())"
```

Record the old and new version values from the MLflow UI and Forecast health
response. Existing orders retain the model version that produced their saved
prediction; new forecasts use the version loaded at startup.

PostgreSQL persists data in the named Compose volume `pgdata`. `docker compose
down` preserves it. `docker compose down -v` deletes the volume and all stored
orders and users; do not use `-v` unless that deletion is intended.

## Secret rotation and missing-secret checks

The expected behavior for key rotation, missing secrets, database-password
rotation, and Forecast API degradation is specified in the lab assignment.
Perform the experiments against a disposable development setup, record actual
commands and results in `REPORT_4/REPORT_4.md`, and restore the expected secrets
afterward.
Replacing `db_password` alone does not change the password of a PostgreSQL
instance whose data volume has already been initialized; database role password
rotation and secret-file updates must be coordinated.

## Development

Dependencies are managed by `uv`:

```bash
uv sync --frozen
```

To run the trainer locally, install the optional training group:

```bash
uv sync --frozen --group training
```

For an integrated local run, use Docker Compose so the services receive their
secrets and can resolve each other by service name:

```bash
docker compose up --build
```

## Useful commands

```bash
docker compose build --no-cache
docker compose logs -f
docker compose down
```

The Compose file builds from the repository root and uses Dockerfiles under
`orders-service/`, `forecast-service/`, `training_service/`, and
`mlflow-service/`.
