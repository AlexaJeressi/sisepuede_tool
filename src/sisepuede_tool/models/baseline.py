import dataclasses
import datetime
from typing import List, Optional

import pandas as pd


@dataclasses.dataclass
class BaselineValidation:
    """Result of validating one uploaded baseline CSV.

    `df` is the sisepuede-validated/interpolated frame (from
    `ModelAttributes.check_projection_input_df`, `strip_dims=False` so
    `region` stays as a column) -- this, not the raw upload, is what should
    be run through Transformations/Strategies/the model, since it's already
    been checked for full time-period coverage.
    """

    ok: bool
    error: Optional[str] = None
    region: Optional[str] = None
    n_time_periods: Optional[int] = None
    interpolated_periods: List[int] = dataclasses.field(default_factory=list)
    df: Optional[pd.DataFrame] = None


@dataclasses.dataclass
class BaselineDataset:
    id: str
    label: str
    df: pd.DataFrame
    region: str
    loaded_at: datetime.datetime
    n_time_periods: int
    interpolated_periods: List[int] = dataclasses.field(default_factory=list)
