"""Loading and validating baseline input CSVs.

Validation is a thin wrapper around `ModelAttributes.check_projection_input_df`,
which does the real work: enforces a single (region, ...) dimensional
combination per file, verifies/interpolates time-period coverage against
`attribute_dim_time_period.csv`, and hands back a frame ready to feed into
`Transformer`/`Transformation`/`Strategy`/`SISEPUEDEModels.project`.
"""

import pathlib
from typing import Union

import pandas as pd
from sisepuede.core.model_attributes import ModelAttributes

from sisepuede_tool.models.baseline import BaselineValidation


def load_csv(path: Union[str, pathlib.Path]) -> pd.DataFrame:
    return pd.read_csv(path)


def validate_baseline(df: pd.DataFrame, model_attributes: ModelAttributes) -> BaselineValidation:
    if model_attributes.dim_time_period not in df.columns:
        return BaselineValidation(
            ok=False,
            error=f"Missing required column '{model_attributes.dim_time_period}'.",
        )
    if model_attributes.dim_region not in df.columns:
        return BaselineValidation(
            ok=False,
            error=f"Missing required column '{model_attributes.dim_region}'.",
        )

    original_periods = set(df[model_attributes.dim_time_period])

    try:
        dict_dims, df_validated, n_periods, periods = model_attributes.check_projection_input_df(
            df,
            interpolate_missing_q=True,
            strip_dims=False,
            drop_invalid_time_periods=True,
        )
    except ValueError as e:
        return BaselineValidation(ok=False, error=str(e))

    region = dict_dims.get(model_attributes.dim_region)
    interpolated_periods = sorted(set(periods) - original_periods)

    return BaselineValidation(
        ok=True,
        region=region,
        n_time_periods=n_periods,
        interpolated_periods=interpolated_periods,
        df=df_validated,
    )


def missing_input_fields(df: pd.DataFrame, model_attributes: ModelAttributes) -> list:
    """Model input fields absent from `df`. sisepuede doesn't reject these at
    validation, but a sector model whose inputs are missing fails at run time
    (e.g. AFOLU on a baseline older than the installed sisepuede), so the
    Baseline page warns about them up front."""
    present = set(df.columns)
    return [f for f in model_attributes.all_variable_fields_input if f not in present]
