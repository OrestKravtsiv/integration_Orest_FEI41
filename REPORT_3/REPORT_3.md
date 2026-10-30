# Laboratory Work 3 Report

## Environment

- Date shown in the verification screenshots: 29.10.2026
- Project: House Price Forecast & Orders API
- Operating system: Windows
- Runtime: Docker Compose
- Deferred-task implementation: FastAPI `BackgroundTasks` (Variant A)
- Evidence: screenshots stored in this folder; the evidence references below use
  their supplied filenames

## Objectives

1. Implement concurrent price forecasts for a batch of orders.
2. Move single-order prediction out of the main HTTP request.
3. Track the prediction lifecycle using `pending`, `priced`, and `failed`.
4. Verify behavior when Forecast API is unavailable and when a task is run again.
5. Record the results and limitations of the in-process background-task option.

## Implementation summary

Orders API now accepts authenticated single-order requests with
`POST /orders`. It saves the order with `status=pending` and
`predicted_price=null`, schedules prediction using FastAPI `BackgroundTasks`,
and responds with `202 Accepted` and a `Location` header. The task opens its
own database session and HTTP client. On completion, it stores the prediction
and sets `priced`; on a forecast error, it sets `failed`.

The authenticated `POST /orders/batch` endpoint concurrently requests
predictions for a list of orders and returns a result for each item. It uses a
shared `httpx.AsyncClient`, applies a forecast timeout, and limits batches to
`BATCH_MAX_ITEMS` (default 50). A failure for one forecast does not prevent
other batch items from being processed. Malformed requests and batches over
the configured limit are rejected with `422`.

PATCH requests that change property features clear the previous prediction,
set the order to `pending`, and schedule a new forecast. Changes to client data
alone do not schedule another forecast. GET responses include the order's
current status.

The `status` column was added to the existing PostgreSQL table using
`orders-service/migrations/001_add_order_status.sql`. Existing rows were
backfilled as `priced` when a prediction was present and `failed` when it was
null.

## Acceptance-test results

| No. | Scenario | Observed result | Status |
|---:|---|---|---|
| 1 | Start Docker Compose | Orders API and Forecast API were up; PostgreSQL was healthy. | Pass — [1.png](./1.png) |
| 2 | Create one order | `POST /orders` returned `202`; order 37 was initially `pending` with a null prediction and a `Location` header. | Pass — [2.png](./2.png) |
| 3 | Retrieve the order | `GET /orders/37` returned `200`, `priced`, and a numeric prediction. | Pass — [3.png](./3.png) |
| 4 | Batch of 10 orders | `POST /orders/batch` returned `200`, `total: 10`, and results with `priced` status. | Pass — [4.png](./4.png) |
| 5 | Batch above the limit | A batch of 51 orders returned `422` with `Batch cannot contain more than 50 orders.` | Pass — [5_2.png](./5_2.png) |
| 6 | Forecast API unavailable | The order was accepted and persisted; subsequent GET showed `failed` and a null prediction. | Pass — [7_1.png](./7_1.png), [7_2.png](./7_2.png) |
| 7 | Update property features | PATCH of `gr_liv_area` returned `202` with `pending` and a null prediction. A later client-only PATCH response showed the order back in `priced` state with a prediction. | Pass — [6_1.png](./6_1.png), [6_2.png](./6_2.png) |
| 8 | Update only client data | PATCH of `client_name` returned `200`; the prediction remained unchanged in the runtime comparison. The screenshot shows the final `priced` order and its prediction. | Pass — [6_2.png](./6_2.png) |
| 9 | Request without an access token | `POST /orders/batch` returned `401 Unauthorized` and `WWW-Authenticate: Bearer`. | Pass — [5_3.png](./5_3.png) |
| 10 | Run the forecast task again | The task was invoked again for existing order 37; the log showed a successful forecast and `result=priced`. A database count comparison before and after the repeated task showed no increase. | Pass — [8.png](./8.png) |

An additional malformed-batch request returned `422` due to a trailing comma
and invalid JSON syntax. This verifies rejection of malformed JSON; a separate
valid JSON item containing an extra, unknown field is not shown in the supplied
screenshots. See [5_1.png](./5_1.png).

## Performance and reliability observations

During runtime verification, one batch of 10 completed in **0.333 s**; ten
separate one-item batch requests took **0.476 s** in total. The batch request
was faster in this run because it sent the independent forecast requests
concurrently and avoided repeated HTTP request overhead. These timings depend
on the local environment and are not visible in the supplied screenshots.

With Variant A, background tasks run in the Orders API process and are not
stored in a durable external queue. If the process is restarted while a task is
pending, the database row remains, but the in-memory task may be lost and the
order may remain `pending`. Celery or ARQ with a message broker and a separate
worker provides a more durable task-execution option, at the cost of additional
infrastructure.

This restart behavior was also checked at runtime: an order was created while
Forecast API was stopped, Orders API was forcibly restarted before the
background task completed, and Forecast API was then restored. The order
remained `pending`, confirming that the process-local task was not recovered.
The temporary test record was removed afterward. A screenshot of this restart
experiment is not included in the supplied evidence folder.

## Screenshot evidence

1. `1.png` — Docker Compose service status.
2. `2.png` — single order accepted with `202`, `pending`, null prediction, and
   `Location`.
3. `3.png` — GET of order 37 after prediction, showing `priced`.
4. `4.png` — batch of 10 with `total: 10` and priced results.
5. `5_1.png` — malformed JSON rejected with `422`.
6. `5_2.png` — 51-item batch rejected with `422`.
7. `5_3.png` — unauthenticated batch request rejected with `401`.
8. `6_1.png` — property-feature PATCH resets the order to `pending`.
9. `6_2.png` — client-name PATCH response.
10. `7_1.png` and `7_2.png` — order creation and final `failed` status while
    Forecast API is unavailable.
11. `8.png` — manual re-execution of the forecast function for order 37.

The screenshots include bearer authorization values in generated cURL
examples. Redact those values before sharing the report or screenshots outside
the local workspace.

## Conclusion

The supplied evidence confirms the main asynchronous-order lifecycle, batch
processing for 10 orders, rejection of a batch over the 50-order limit,
authentication enforcement, PATCH behavior, and handling of Forecast API
unavailability. FastAPI `BackgroundTasks` is sufficient for the required
basic deferred workflow, but it does not provide durable execution across
Orders API restarts. Runtime timing measurements and the before/after database
count check for the repeated-task test are recorded above; screenshots of those
measurements and of the restart experiment were not included in the supplied
evidence folder.
