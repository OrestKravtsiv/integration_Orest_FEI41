import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBRegressor

NUMERIC = [
    "GrLivArea",
    "TotalBsmtSF",
    "GarageArea",
    "YearBuilt",
    "OverallQual",
]
CATEGORICAL = ["MSZoning"]
FEATURES = NUMERIC + CATEGORICAL
TARGET = "SalePrice"
SEED = 42


def build_ridge_model() -> Pipeline:
    """Build the existing Ridge baseline pipeline."""
    preprocessor = ColumnTransformer(
        [
            (
                "num",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                NUMERIC,
            ),
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                CATEGORICAL,
            ),
        ]
    )
    return Pipeline(
        [
            ("preprocess", preprocessor),
            ("regressor", Ridge(alpha=1.0)),
        ]
    )


def build_xgboost_model(params: dict[str, int | float]) -> Pipeline:
    """Build the imputation, encoding, and log-target XGBoost pipeline."""
    preprocessor = ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="median"), NUMERIC),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore"),
                CATEGORICAL,
            ),
        ]
    )
    regressor = XGBRegressor(
        **params,
        random_state=SEED,
        n_jobs=1,
        objective="reg:squarederror",
        verbosity=0,
    )
    return Pipeline(
        [
            ("prep", preprocessor),
            (
                "model",
                TransformedTargetRegressor(
                    regressor=regressor,
                    func=np.log1p,
                    inverse_func=np.expm1,
                ),
            ),
        ]
    )


def load_training_data(path: str) -> pd.DataFrame:
    """Load and validate the Ames Housing dataset."""
    data = pd.read_csv(path)
    data.columns = data.columns.str.strip()
    required = set(FEATURES + [TARGET])
    missing = required - set(data.columns)
    if missing:
        raise ValueError(
            f"Training dataset is missing columns: {sorted(missing)}"
        )
    data = data[FEATURES + [TARGET]].dropna(subset=[TARGET]).copy()
    data[NUMERIC] = data[NUMERIC].astype("float64")
    return data
