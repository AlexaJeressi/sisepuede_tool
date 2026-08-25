"""Loading a validation (observed) dataset + its required crosswalk, and
comparing it against a model run.

Crosswalk shape: one row per (comparison_id, validation_field,
sisepuede_output_field) triple. Multiple rows sharing a comparison_id
express many-to-many aggregation -- e.g. one observed series compared
against the sum of several model output columns. See
resources/ (no shipped example; users bring their own) and the plan doc for
the full rationale.
"""

import dataclasses
import pathlib
from typing import Dict, Union

import numpy as np
import pandas as pd

from sisepuede_tool.models.crosswalk_validation import CrosswalkValidation

REQUIRED_CROSSWALK_COLUMNS = ["comparison_id", "comparison_label", "validation_field", "sisepuede_output_field"]


def load_validation_dataset(path: Union[str, pathlib.Path]) -> pd.DataFrame:
    return pd.read_csv(path)


def load_crosswalk(path: Union[str, pathlib.Path]) -> pd.DataFrame:
    return pd.read_csv(path)


def validate_crosswalk(
    crosswalk_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    output_catalog: pd.DataFrame,
) -> CrosswalkValidation:
    missing_columns = [c for c in REQUIRED_CROSSWALK_COLUMNS if c not in crosswalk_df.columns]
    if missing_columns:
        return CrosswalkValidation(ok=False, errors=[f"Crosswalk missing column(s): {missing_columns}"])

    if "time_period" not in validation_df.columns:
        return CrosswalkValidation(ok=False, errors=["Validation dataset missing 'time_period' column."])

    known_output_fields = set(output_catalog["variable"])
    validation_columns = set(validation_df.columns)

    errors = []
    bad_comparison_ids = set()
    for _, row in crosswalk_df.iterrows():
        cid = row["comparison_id"]
        if row["validation_field"] not in validation_columns:
            errors.append(
                f"comparison_id '{cid}': validation_field '{row['validation_field']}' "
                "not found in the validation dataset's columns."
            )
            bad_comparison_ids.add(cid)
        if row["sisepuede_output_field"] not in known_output_fields:
            errors.append(
                f"comparison_id '{cid}': sisepuede_output_field '{row['sisepuede_output_field']}' "
                "is not a known SISEPUEDE output variable."
            )
            bad_comparison_ids.add(cid)

    all_comparison_ids = set(crosswalk_df["comparison_id"])
    valid_comparison_ids = sorted(all_comparison_ids - bad_comparison_ids)

    return CrosswalkValidation(ok=len(errors) == 0, errors=errors, comparison_ids=valid_comparison_ids)


def comparison_label(crosswalk_df: pd.DataFrame, comparison_id: str) -> str:
    rows = crosswalk_df[crosswalk_df["comparison_id"] == comparison_id]
    if rows.empty:
        return comparison_id
    return rows.iloc[0]["comparison_label"] or comparison_id


def aggregate_comparison(
    crosswalk_df: pd.DataFrame,
    comparison_id: str,
    df_output: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> pd.DataFrame:
    """Long-format [time_period, series, value] with series in
    {"observed", "modeled"} for one comparison_id -- sums the distinct
    validation_field columns for "observed" and the distinct
    sisepuede_output_field columns for "modeled"."""
    rows = crosswalk_df[crosswalk_df["comparison_id"] == comparison_id]
    validation_fields = [f for f in rows["validation_field"].unique() if f in validation_df.columns]
    output_fields = [f for f in rows["sisepuede_output_field"].unique() if f in df_output.columns]

    frames = []
    if validation_fields:
        observed = pd.DataFrame(
            {
                "time_period": validation_df["time_period"],
                "series": "observed",
                "value": validation_df[validation_fields].sum(axis=1),
            }
        )
        frames.append(observed)
    if output_fields:
        modeled = pd.DataFrame(
            {
                "time_period": df_output["time_period"],
                "series": "modeled",
                "value": df_output[output_fields].sum(axis=1),
            }
        )
        frames.append(modeled)

    if not frames:
        return pd.DataFrame(columns=["time_period", "series", "value"])
    return pd.concat(frames, ignore_index=True)


def compute_fit_metrics(comparison_frame: pd.DataFrame) -> Dict[str, float]:
    """RMSE/MAE/bias between the "observed" and "modeled" series in a frame
    from aggregate_comparison, over their overlapping time periods. Returns
    an empty dict if either series is missing or they don't overlap."""
    observed = comparison_frame[comparison_frame["series"] == "observed"].set_index("time_period")["value"]
    modeled = comparison_frame[comparison_frame["series"] == "modeled"].set_index("time_period")["value"]

    common_periods = observed.index.intersection(modeled.index)
    if len(common_periods) == 0:
        return {}

    diff = modeled.loc[common_periods] - observed.loc[common_periods]
    return {
        "rmse": float(np.sqrt((diff**2).mean())),
        "mae": float(diff.abs().mean()),
        "bias": float(diff.mean()),
    }
