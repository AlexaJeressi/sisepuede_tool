import dataclasses
from typing import Optional

import pandas as pd


@dataclasses.dataclass
class RunResult:
    strategy_id: int
    baseline_id: str
    ok: bool
    df_output: Optional[pd.DataFrame] = None
    error: Optional[str] = None
    elapsed_seconds: float = 0.0
