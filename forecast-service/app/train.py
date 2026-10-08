"""Train the model, evaluate it on held-out data, and persist the artifact."""

from pathlib import Path

import joblib
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from .model import (
    CAT,
    NUM,
    TARGET,
    load_training_data,
    train_model,
)


ARTIFACTS = (
    Path(__file__).resolve().parent.parent
    / "artifacts"
)


def main() -> None:
    """Train the model, report honest metrics, and persist the artifact."""

    df = load_training_data()

    train_df, test_df = train_test_split(
        df,
        test_size=0.2,
        random_state=42,
    )

    # Evaluation-only model: fit strictly on the training split so the
    # test split stays unseen during fitting.
    eval_model = train_model(train_df)

    train_pred = eval_model.predict(train_df[NUM + CAT])
    test_pred = eval_model.predict(test_df[NUM + CAT])

    train_r2 = r2_score(train_df[TARGET], train_pred)
    train_mae = mean_absolute_error(train_df[TARGET], train_pred)

    test_r2 = r2_score(test_df[TARGET], test_pred)
    test_mae = mean_absolute_error(test_df[TARGET], test_pred)

    print(f"[train] Train (in-sample): R2={train_r2:.4f}, MAE={train_mae:.0f} USD")
    print(f"[train] Test  (hold-out):  R2={test_r2:.4f}, MAE={test_mae:.0f} USD")

    if (train_r2 - test_r2) > 0.05 or test_mae > train_mae * 1.2:
        print(
            "[train] Warning: noticeable gap between train and test "
            "metrics - possible overfitting."
        )
    else:
        print(
            "[train] Train and test metrics are close - no strong "
            "evidence of overfitting."
        )

    # Final artifact is trained on the FULL dataset (train + test) to make
    # the best use of available data once the honest evaluation above is
    # already recorded.
    model = train_model(df)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACTS / "model.pkl"
    joblib.dump(model, artifact_path)

    print(f"[train] artifact persisted: {artifact_path}")


if __name__ == "__main__":
    main()