"""Definition of the model and preprocessing pipeline for Ames Housing."""

from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


DATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "ames_train.csv"
)

# Internal feature names used by the model.
# These names match the API-to-model contract.
NUM = [
    "GrLivArea",
    "TotalBsmtSF",
    "GarageArea",
    "YearBuilt",
    "OverallQual",
]

CAT = ["MSZoning"]
TARGET = "SalePrice"

# Column names used by the Ames Housing CSV.
CSV_COLUMNS = {
    "GrLivArea": "GrLivArea",
    "TotalBsmtSF": "TotalBsmtSF",
    "GarageArea": "GarageArea",
    "YearBuilt": "YearBuilt",
    "OverallQual": "OverallQual",
    "MSZoning": "MSZoning",
    "SalePrice": "SalePrice",
}


def load_training_data() -> pd.DataFrame:
    """Load and normalize the Ames Housing training dataset.

    The source CSV uses column names with spaces, while the application
    uses normalized column names without spaces.
    """
    df = pd.read_csv(DATA_PATH)

    # Remove accidental whitespace around column names.
    df.columns = df.columns.str.strip()

    missing_columns = set(CSV_COLUMNS) - set(df.columns)

    if missing_columns:
        raise ValueError(
            "Training dataset is missing required columns: "
            f"{sorted(missing_columns)}"
        )

    df = df.rename(columns=CSV_COLUMNS)

    columns = NUM + CAT + [TARGET]

    return df[columns].dropna(subset=[TARGET])


def train_model(df: pd.DataFrame | None = None) -> Pipeline:
    """Build and train the Ridge regression pipeline.

    If ``df`` is not provided, the full training dataset is loaded from
    disk (used for the final production model and for standalone/dev
    runs). If ``df`` is provided, the pipeline is fit on exactly that
    subset (used for train/test evaluation).
    """
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
                NUM,
            ),
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                CAT,
            ),
        ]
    )

    pipe = Pipeline(
        [
            ("preprocess", preprocessor),
            ("regressor", Ridge(alpha=1.0)),
        ]
    )

    if df is None:
        df = load_training_data()

    pipe.fit(df[NUM + CAT], df[TARGET])

    return pipe