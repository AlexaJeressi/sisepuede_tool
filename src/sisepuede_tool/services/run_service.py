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

NemoMod status: when NemoMod finds no solution (e.g. INFEASIBLE) sisepuede
doesn't raise. It fills the electricity outputs with 0 and the run completes,
saying so only through its logger ("NemoMod run failed with result ...").
The models get SISEPUEDE_LOGGER, and run_combination() reads that message
into RunResult.nemomod_status, so the run is kept but can be flagged.
"""

import logging
import re
import time
from typing import List, Optional

import pandas as pd
import sisepuede.transformers as trf
from sisepuede.core.model_attributes import ModelAttributes
from sisepuede.manager.sisepuede_models import SISEPUEDEModels

from sisepuede_tool import config
from sisepuede_tool.models.run_result import RunResult

# sisepuede's own log: kept apart from the tool's (it logs every model step at
# INFO); its warnings and errors still reach the console
SISEPUEDE_LOGGER = logging.getLogger("sisepuede")
SISEPUEDE_LOGGER.setLevel(logging.INFO)
SISEPUEDE_LOGGER.propagate = False
if not SISEPUEDE_LOGGER.handlers:
    _console = logging.StreamHandler()
    _console.setLevel(logging.WARNING)
    _console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    SISEPUEDE_LOGGER.addHandler(_console)

# messages of sisepuede's EnergyProduction.project() after NemoMod runs; the
# result is Julia's status as text (e.g. "OPTIMAL", "INFEASIBLE",
# "INFEASIBLE::TerminationStatusCode = 2"; "None" when NemoMod raised)
_NEMOMOD_OK = re.compile(r"NemoMod ran successfully with the following status: (.+)$", re.S)
_NEMOMOD_FAILED = re.compile(r"NemoMod run failed with result (.+?)\. Populating", re.S)


def _status_name(text: str) -> str:
    """'INFEASIBLE::TerminationStatusCode = 2' -> 'INFEASIBLE'; 'None' -> 'NO_RESULT'."""
    m = re.search(r"[A-Z][A-Z_]{3,}", text)
    return m.group(0) if m else ("NO_RESULT" if text.strip() in ("", "None") else text.strip())


class _NemoModStatus(logging.Handler):
    """Collects the NemoMod statuses sisepuede logs while it is attached
    (a failure is never OPTIMAL, whatever its text)."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.statuses: List[str] = []

    def emit(self, record):
        msg = record.getMessage()
        m = _NEMOMOD_OK.search(msg)
        if m:
            self.statuses.append(_status_name(m.group(1)))
            return
        m = _NEMOMOD_FAILED.search(msg)
        if m:
            name = _status_name(m.group(1))
            self.statuses.append("FAILED" if name == "OPTIMAL" else name)


def nemomod_status(statuses: List[str]) -> Optional[str]:
    """One status for a run (NemoMod can run once per region): the first that
    isn't OPTIMAL, else OPTIMAL; None when NemoMod didn't run."""
    bad = [s for s in statuses if s.upper() != "OPTIMAL"]
    return bad[0] if bad else (statuses[0] if statuses else None)


def build_models(model_attributes: ModelAttributes) -> SISEPUEDEModels:
    return SISEPUEDEModels(
        model_attributes,
        allow_electricity_run=True,
        fp_julia=str(config.JULIA_DIR),
        fp_nemomod_reference_files=str(config.NEMOMOD_REFERENCE_DIR),
        initialize_julia=True,
        logger=SISEPUEDE_LOGGER,
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
    status = _NemoModStatus()
    SISEPUEDE_LOGGER.addHandler(status)
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
            df_input=df_transformed,
            elapsed_seconds=time.time() - t0,
            nemomod_status=nemomod_status(status.statuses),
        )
    except Exception as e:
        return RunResult(
            strategy_id=strategy_id,
            baseline_id=baseline_id,
            ok=False,
            error=str(e),
            elapsed_seconds=time.time() - t0,
            nemomod_status=nemomod_status(status.statuses),
        )
    finally:
        SISEPUEDE_LOGGER.removeHandler(status)
