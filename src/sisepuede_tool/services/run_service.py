"""Eager SISEPUEDEModels construction and per-(strategy, baseline) execution.

Julia is connected at construction time (`initialize_julia=True`), not
deferred to first run -- confirmed working via a standalone spike (~70s on
a cold Julia environment; much faster once Julia's packages are installed
and precompiled). The only per-run toggle is `include_nemo_fuel_production`,
which controls whether the Energy Production (NemoMod electricity)
sub-model actually executes on a given call -- it does not affect whether
Julia itself is loaded.

Known caveat from the M0 spike: NemoMod.jl currently throws a
"Method overwriting is not permitted during Module precompilation" error
during Julia precompilation. It did not prevent `SISEPUEDEModels`
construction, but electricity-production runs (M4) should be verified
end-to-end since this could affect NemoMod's actual solve step.
"""

import time
from typing import List, Optional

import pandas as pd
import sisepuede.transformers as trf
from sisepuede.core.model_attributes import ModelAttributes
from sisepuede.manager.sisepuede_models import SISEPUEDEModels

from sisepuede_tool import config
from sisepuede_tool.models.run_result import RunResult


def build_models(model_attributes: ModelAttributes) -> SISEPUEDEModels:
    return SISEPUEDEModels(
        model_attributes,
        allow_electricity_run=True,
        fp_julia=str(config.JULIA_DIR),
        fp_nemomod_reference_files=str(config.NEMOMOD_REFERENCE_DIR),
        initialize_julia=True,
    )


def run_combination(
    models: SISEPUEDEModels,
    strategy: trf.Strategy,
    df_baseline: pd.DataFrame,
    region: str,
    run_energy_production: bool,
    strategy_id: int,
    baseline_id: str,
    models_run: Optional[List[str]] = None,
) -> RunResult:
    """Apply `strategy` to `df_baseline` and run it through the model.

    Never raises -- any failure (including a bug in a specific transformer's
    math, or in a sector model itself, per the known upstream issues) is
    captured into the returned RunResult so one failing combination in a
    batch doesn't lose the others. `models_run` lets a caller exclude a
    known-broken sector (e.g. AFOLU, see the LivestockDietEstimator issue)
    without abandoning the whole run.
    """
    t0 = time.time()
    try:
        df_transformed = strategy(df_input=df_baseline)
        df_output = models.project(
            df_transformed,
            regions=[region],
            include_nemo_fuel_production=run_energy_production,
            check_results=True,
            models_run=models_run,
        )
        return RunResult(
            strategy_id=strategy_id,
            baseline_id=baseline_id,
            ok=True,
            df_output=df_output,
            elapsed_seconds=time.time() - t0,
        )
    except Exception as e:
        return RunResult(
            strategy_id=strategy_id,
            baseline_id=baseline_id,
            ok=False,
            error=str(e),
            elapsed_seconds=time.time() - t0,
        )
