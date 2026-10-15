# Lab 2 report

This report records implementation checks and Docker Compose test observations.
Results marked pending still require execution or collection of measurements.

## Environment

- Date: 16.10.2026
- OS / Docker Engine / Docker Compose versions: Windows; Docker Engine 29.8.0

## Acceptance tests T1–T12

Record the exact command or request, observed result, and pass/fail status.
Never paste secret values or access tokens into this report.

| Test | Expected result | Observed result | Status |
|---|---|---|---|
| T1 `docker compose config` | No secret values; Forecast API has no published ports | Compose config validation passed; Forecast container has no host binding; secret values absent from resolved runtime configuration | Pass |
| T2 Inspect Orders API environment | No secret values in environment | Checked running container: neither secret value nor `DATABASE_URL` is in its environment | Pass |
| T3 Start without `secrets/db_password` | Startup is refused | Compose warned that the source file was missing and created the containers; Orders API then failed during startup because `/run/secrets/db_password` was unavailable/unreadable. The secret file was restored afterward. | Pass (Orders API startup refused) |
| T4 Host request to `localhost:8001/health` | Connection refused | Host request failed to connect; Compose reports no published port | Pass |
| T5 Register valid user | 201 and public user fields only | Runtime registration returned 201; response omitted `hashed_password` | Pass |
| T6 Login with valid/invalid credentials | 200 for valid credentials; 401 with identical error for either invalid case | Runtime valid login returned a token; wrong-password and unknown-user responses were identical 401 | Pass |
| T7 Anonymous `GET /orders` | 401 and `WWW-Authenticate: Bearer` | Runtime request returned 401 with `WWW-Authenticate: Bearer` | Pass |
| T8 Authenticated `POST /orders` | 201 | Runtime request returned 201 and a non-null prediction from Forecast API | Pass |
| T9 Authenticated PATCH changing property features | 200 and prediction re-requested | Runtime PATCH returned 200; prediction changed after the feature update | Pass |
| T10 Authenticated DELETE | 204 | Runtime DELETE returned 204 | Pass |
| T11 Rotate JWT key and retry old token | Old token rejected with 401 after service restart | After replacing the JWT secret and recreating `orders-api`, the old token returned HTTP 401. | Pass |
| T12 Stop Forecast API; authenticated `POST /orders` | 201 with `predicted_price: null` | Stopped Forecast API; authenticated POST returned HTTP 201, order ID 6, and an empty PowerShell display for the JSON null prediction. Forecast API was started again afterward. | Pass |

## Integration experiments R3.2–R3.5

### R3.2 — JWT signing-key rotation

- Procedure: obtain a token, verify it against `/auth/me`, replace
  `secrets/jwt_secret_key` with a new random key, recreate `orders-api`, then
  request `/auth/me` using the old token.
- Response before rotation: `/auth/me` returned HTTP 200 for the test user.
- Response after rotation with the old token: HTTP 401.
- Conclusion: rotating the signing key and recreating Orders API invalidated
  the previously issued token.

The secret file was updated in place and `orders-api` was recreated.

### R3.3 — Missing secret

- Procedure: stop the stack, temporarily move `secrets/db_password` outside the
  secrets directory, then attempt `docker compose up`.
- Secret removed (do not include its former value): `secrets/db_password` was
  temporarily moved to a backup name.
- Startup command and observed error: `docker compose up` warned that the
  declared secret source file did not exist and created the services. Orders API
  then failed during startup when reading `/run/secrets/db_password`; the file
  was restored before continuing.
- Comparison with passing a password through `.env`: a password in `.env`
  would be supplied as an environment value rather than a mounted secret file.
  The missing-file experiment confirms the file-based configuration prevents
  Orders API from starting with a missing secret.

### R3.4 — Database-password rotation

- Development procedure: back up the disposable volume; connect to PostgreSQL
  with an administrator and change the database role password interactively
  (for example, `\password orders` in `psql`); update `secrets/db_password`;
  recreate the containers so Orders API reads the new mount; verify connections.
  Do not remove the volume merely to rotate a password.
- Production procedure: coordinate rotation with the database owner. A common
  low-downtime approach is to create a replacement role with the required
  privileges, deploy its credential through the secret mechanism, roll/recreate
  API instances and verify them, then revoke the old role. If the same role must
  be retained, schedule and coordinate the database-side password change with
  application secret deployment and restart. Back up and monitor the database;
  never delete the data volume as a rotation method.
- Observed procedure and results: saved the original secret in the current
  PowerShell session, generated and wrote a temporary random value to
  `secrets/db_password`, then recreated `postgres` and `orders-api` without
  removing the volume. PostgreSQL remained healthy. Orders API exited with
  `password authentication failed for user "orders"`.
- Confirm whether the Compose secret change alone altered the existing database
  role password: No. The observed authentication failure confirmed that
  PostgreSQL continued using its initialized role password. The original secret
  was subsequently restored and Orders API was recreated.

`POSTGRES_PASSWORD_FILE` initializes the password only when PostgreSQL creates
the data directory. On subsequent starts, PostgreSQL uses the password already
stored in its catalog; changing the file alone does not alter that password.

### R3.5 — Forecast API unavailable

- Procedure: stop only `forecast-api`, then send a valid authenticated
  `POST /orders` request to Orders API.
- How Forecast API was stopped: `docker compose stop forecast-api`.
- Authenticated request and observed status: test user logged in and sent
  `POST /orders`; response was HTTP 201 and created order ID 6.
- Confirm `predicted_price` was `null`: yes; PowerShell displayed the null
  property as an empty value. Forecast API was started afterward.

## Local implementation checks

An isolated FastAPI `TestClient` check using an in-memory SQLite database
passed: public health, registration, duplicate-user conflict, rejection of
extra registration fields, Argon2 password verification, form-encoded login,
identical 401 login errors, bearer-token access, order creation/list/delete,
and PATCH-triggered prediction refresh. The Forecast call and secret-file read
were mocked. This check does not replace the Docker/PostgreSQL acceptance tests
above.

## Model evaluation

The model was evaluated using a held-out test split. The final artifact was
trained on the full dataset after the evaluation.

| Split | R² | MAE (USD) |
|---|---:|---:|
| Train (in-sample) | 0.7605 | 23,771 |
| Hold-out test | 0.7994 | 24,276 |

The train and hold-out metrics are close. The test R² is slightly higher, while
the test MAE is USD 505 higher than the training MAE. These results show no
strong evidence of overfitting in this split.

## Control questions

1. Environment variables can leak through process inspection (for example,
   `/proc`), container inspection, diagnostic/crash dumps, logs, child-process
   environments, and deployment/monitoring metadata.
2. `MODEL_VERSION`, `FORECAST_TIMEOUT`, `POSTGRES_USER`, and
   `ACCESS_TOKEN_EXPIRE_MINUTES` are configuration. `db_password` and
   `jwt_secret_key` are secrets because disclosure enables database access or
   token forgery.
3. In ordinary Docker Compose, file-backed secrets are distributed from host
   files and mounted into service containers; this is useful configuration
   hygiene, not a centralized secret vault. Docker Swarm manages secrets as
   cluster objects and distributes them only to authorized service tasks, with
   encrypted storage/transport and in-memory mounts on Linux workers.
4. `POSTGRES_PASSWORD_FILE` is consumed by the official image during first
   database initialization. Once initialized, the database role password is
   stored inside PostgreSQL and is not reset by changing that file. For
   development, change the role password in PostgreSQL, update the secret, and
   recreate containers without deleting the volume. For production, use a
   coordinated credential rollout—preferably a replacement role, rolling
   application update, verification, and revocation of the old role—or schedule
   a coordinated password change with backups and monitoring.
5. SHA-256 is deliberately fast, making password guessing cheap. Argon2id and
   bcrypt are adaptive password-hashing algorithms designed to make guessing
   expensive; Argon2id is also memory-hard. A salt is a unique random value
   stored with each password hash so identical passwords hash differently and
   precomputed rainbow tables are ineffective. The work factor controls the
   computational (and, for Argon2id, memory) cost.
6. A JWT is three Base64URL-encoded parts: header, payload, and signature,
   separated by dots. The signature authenticates the header and payload;
   changing a claim without a valid re-signature makes verification fail.
7. An `alg: none` attack attempts to use an unsigned token; algorithm confusion
   tricks a verifier into interpreting a token with an unintended algorithm or
   key type. This service decodes with an explicit allow-list
   `algorithms=["HS256"]` and signs only with HS256.
8. 401 means the request lacks valid authentication. `WWW-Authenticate`
   advertises the authentication scheme; protected routes return
   `WWW-Authenticate: Bearer`, prompting a client to provide a bearer token.
9. JWTs signed with the old `jwt_secret_key` fail signature verification after
   Orders API restarts with a new key; clients must log in again to obtain new
   tokens.
10. Identical login errors reduce username enumeration: an attacker cannot use
    distinct server messages to determine whether a username exists.
11. `/health` is public so operators and orchestrators can check service
    liveness without user credentials. Forecast API is internal so the Orders
    API remains the single externally accessible business-service entry point.
12. A signed JWT is validated locally without a server-side token session, so
    authentication is stateless. Individual tokens cannot normally be revoked
    before expiry without adding state (such as a denylist); rotating the
    signing key invalidates all tokens signed by the old key.
