import dataclasses
from typing import Optional

import pandas as pd


@dataclasses.dataclass
class RunResult:
    strategy_id: int
    baseline_id: str
    ok: bool
    df_output: Optional[pd.DataFrame] = None
    df_input: Optional[pd.DataFrame] = None
    error: Optional[str] = None
    elapsed_seconds: float = 0.0
    # NemoMod's result ("OPTIMAL", "INFEASIBLE", ...); None when it didn't run
    nemomod_status: Optional[str] = None
    # the pathway's last historical year NemoMod ran with; None = sisepuede's default (first year)
    base_year: Optional[int] = None

    @property
    def nemomod_failed(self) -> bool:
        """NemoMod ran without a solution: sisepuede completed the run with the
        electricity outputs filled with 0, so they are not real."""
        return self.nemomod_status is not None and self.nemomod_status.upper() != "OPTIMAL"
