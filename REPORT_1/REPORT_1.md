# Laboratory Work 1 Report

## Environment

- Date evidenced by HTTP response screenshots: 24.09.2026
- Project: House Price Forecast & Orders API
- Operating system: Windows
- Docker Engine: 29.8.0
- Docker Compose: 5.5.1
- uv: 0.12.15
- Dataset: Ames Housing training dataset (`ames_train.csv`)
- Evidence: screenshots supplied with the report; summarized in the test table below

## Objectives

1. Investigate the interaction between Orders API and Forecast API and preserve
   graceful degradation when the forecasting service is unavailable.
2. Extend `PATCH /orders/{id}` to update property features and request a new
   price prediction.
3. Evaluate the forecasting model using a train/test split and compare training
   and hold-out metrics.

## Implementation summary

### Service startup and graceful degradation

The initial Compose configuration made Orders API depend on Forecast API being
healthy. This meant an unavailable or unhealthy Forecast API could prevent
Orders API from starting, even though Orders API is intended to create orders
without a prediction when forecasting is unavailable.

The Compose dependency was changed to wait for Forecast API to start rather than
to become healthy. Forecast requests remain internal to the Compose network at
`http://forecast-api:8001`. The order endpoint keeps the order when the
prediction request fails and stores a null `predicted_price`.

### Property updates

The PATCH input schema was extended with the property features used by the
forecast model: `gr_liv_area`, `total_bsmt_sf`, `garage_area`, `year_built`,
`overall_qual`, and `ms_zoning`. When any of these fields changes, Orders API
builds the complete feature payload from the updated and existing values,
requests a new forecast, and stores the returned prediction. If Forecast API is
unavailable, the update is still persisted and the prediction is null.

### Model evaluation

Training now evaluates the model on a held-out test split. The evaluation model
is fitted on the training partition; after evaluation, the final artifact is
trained on the full dataset.

## Verification results

| Requirement | Verification and observed result | Status |
|---|---|---|
| Project setup and tooling | Cloned the repository, copied `.env.example` to `.env` using the Windows `copy` command after the Unix `cp` command was unavailable, and confirmed Docker 29.8.0, Compose 5.5.1, and uv 0.12.15. | Pass |
| Compose service configuration | `docker compose config` showed Orders API reaching Forecast API using `http://forecast-api:8001`; initial configuration also showed the Forecast API host port mapping and a health-based startup dependency. | Pass |
| Graceful handling of unavailable Forecast API | With Forecast API unavailable, `POST /orders` returned HTTP 201 and a JSON response with `"predicted_price": null`. | Pass |
| Orders API availability independent of Forecast health | The initial attempt to start with an unhealthy Forecast API was blocked by the health dependency. The dependency condition was changed to `service_started`; the subsequent order request succeeded without a prediction. | Pass |
| PATCH client field | `PATCH /orders/6` with a client-name update returned HTTP 200 and the updated order. | Pass |
| PATCH property features and refreshed forecast | `PATCH /orders/6` with property features returned HTTP 200; the response showed updated property values and a numeric predicted price. | Pass |
| Train/test model evaluation | Training output reported train R² 0.7605 and MAE 23,771 USD; hold-out test R² 0.7994 and MAE 24,276 USD. The output reported no strong evidence of overfitting. | Pass |
| Model artifact | Training persisted the final model artifact at `/app/artifacts/model.pkl`. | Pass |

## Model metrics

| Split | R² | MAE (USD) |
|---|---:|---:|
| Train (in-sample) | 0.7605 | 23,771 |
| Hold-out test | 0.7994 | 24,276 |

The hold-out test MAE is USD 505 higher than the training MAE, while the test
R² is slightly higher than the training R². The metrics are close and do not
show strong evidence of overfitting on this split. The hold-out results provide
a more useful estimate of performance on unseen data than training-only
metrics.

## Conclusion

The Orders API was verified to create orders when Forecast API was unavailable,
returning a null prediction rather than losing the order. The PATCH operation
was verified for client and property updates, including obtaining a refreshed
prediction when property features changed. The model was evaluated on a
held-out partition, and the reported train/test metrics were close.

## Screenshot evidence

The screenshots provided for this report document the following steps and
results:

1. Repository clone, tool versions, and creation of `.env` from the example.
2. Initial resolved Compose configuration.
3. Continuation of the Compose dependency/configuration output.
4. Order creation returning HTTP 201 with a null predicted price and container
   status.
5. Initial startup attempt with Forecast API overridden to remain unavailable;
   Compose reported the health dependency failure.
6. Successful order creation with null prediction after adjusting the
   Forecast API dependency condition.
7. PATCH schema, CRUD logic, and endpoint changes for property features.
8. HTTP 200 response after PATCH changed property features and returned a new
   prediction.
9. Training and hold-out evaluation metrics and persisted model artifact.
