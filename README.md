# House Price Forecast & Orders API

A Docker Compose application with an Orders API, an internal Forecast API, and
PostgreSQL. Orders API is the only externally published service. It authenticates
users with JWT bearer tokens and requests property-price predictions internally.

## Services and access

| Service | Access |
|---|---|
| Orders API | Host port `${ORDERS_PORT:-8000}` |
| Forecast API | Internal only, `http://forecast-api:8001` |
| PostgreSQL | Internal only, service `postgres:5432` |

Public Orders API routes:

| Method | Route | Access |
|---|---|---|
| GET | `/health` | Public |
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
- The training file `forecast-service/data/ames_train.csv`
- `uv` for local dependency management (optional when using Docker)

The CSV must include `GrLivArea`, `TotalBsmtSF`, `GarageArea`, `YearBuilt`,
`OverallQual`, `MSZoning`, and `SalePrice`.

## Configuration and secrets

Copy `.env.example` to `.env` and set non-secret configuration only:

```env
POSTGRES_USER=orders
POSTGRES_DB=orders
ORDERS_PORT=8000
MODEL_VERSION=v0.1.0
FORECAST_TIMEOUT=3.0
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Do not put database passwords or JWT signing keys in `.env`. Follow
[`secrets/README.md`](secrets/README.md) to provision `secrets/db_password` and
`secrets/jwt_secret_key`. Real secret files are gitignored and mounted read-only
at `/run/secrets/`. The Orders API fails at startup if a required secret is
missing or empty. Secret values are not build arguments, environment variables,
or image contents.

## Start and verify

From the repository root, after creating `.env` and both secret files:

```bash
docker compose up --build
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

All `/orders` requests require the bearer token. PATCH requests that change
property features request a new prediction. If the Forecast API is unavailable,
order creation continues with `predicted_price: null`, preserving graceful
degradation.

In Swagger UI (`/docs`), use **Authorize**. The OAuth2 token URL is
`/auth/login`.

## Data and model

The Forecast API trains a scikit-learn Ridge regression pipeline during its
image build and saves the model artifact in the image. Training reports metrics
for a held-out test split as well as the training split; use those measured
values in `REPORT.md` rather than assuming sample numbers.

PostgreSQL persists data in the named Compose volume `pgdata`. `docker compose
down` preserves it. `docker compose down -v` deletes the volume and all stored
orders and users; do not use `-v` unless that deletion is intended.

## Secret rotation and missing-secret checks

The expected behavior for key rotation, missing secrets, database-password
rotation, and Forecast API degradation is specified in the lab assignment.
Perform the experiments against a disposable development setup, record actual
commands and results in `REPORT.md`, and restore the expected secrets afterward.
Replacing `db_password` alone does not change the password of a PostgreSQL
instance whose data volume has already been initialized; database role password
rotation and secret-file updates must be coordinated.

## Development

Dependencies are managed by `uv`:

```bash
uv sync --frozen
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

The Compose file builds from the repository root and uses the service Dockerfiles
under `orders-service/` and `forecast-service/`.
