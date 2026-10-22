"""NemoMod status read from sisepuede's log (services/run_service.py): a run
whose electricity model has no solution completes, but is flagged."""

import functools
import logging

from sisepuede_tool.models.run_result import RunResult
from sisepuede_tool.services import run_service as rs


@functools.lru_cache(maxsize=1)
def _model_attributes():
    from sisepuede_tool.services import catalog_service

    return catalog_service.build_model_attributes()


def _statuses(*messages):
    h = rs._NemoModStatus()
    for m in messages:
        h.emit(logging.LogRecord("sisepuede", logging.INFO, "", 0, m, None, None))
    return h.statuses


def test_reads_sisepuede_messages():
    assert _statuses("NemoMod ran successfully with the following status: OPTIMAL") == ["OPTIMAL"]
    assert _statuses("NemoMod run failed with result INFEASIBLE. Populating missing data with value 0.0.") == ["INFEASIBLE"]
    assert _statuses("NemoMod run failed with result INFEASIBLE::TerminationStatusCode = 2. Populating missing data with value 0.") == ["INFEASIBLE"]
    assert _statuses("NemoMod run failed with result None. Populating missing data with value 0.") == ["NO_RESULT"]
    assert _statuses("Running AFOLU model", "Unable to retrieve energy demand by fuel in ENTC.") == []


def test_one_status_per_run():
    assert rs.nemomod_status([]) is None
    assert rs.nemomod_status(["OPTIMAL"]) == "OPTIMAL"
    assert rs.nemomod_status(["OPTIMAL", "INFEASIBLE"]) == "INFEASIBLE"


def test_run_result_flag():
    assert not RunResult(0, "b", True).nemomod_failed  # NemoMod off
    assert not RunResult(0, "b", True, nemomod_status="OPTIMAL").nemomod_failed
    assert RunResult(0, "b", True, nemomod_status="INFEASIBLE").nemomod_failed


def test_time_periods_base_from_the_last_historical_year():
    ma = _model_attributes()
    assert rs.time_periods_base(ma, None) is None
    assert rs.time_periods_base(ma, 2017) == [0, 1, 2]  # NDC
    assert rs.time_periods_base(ma, 2026) == list(range(12))  # LEP


class _Models:
    """Records what project() is called with."""

    def __init__(self, model_attributes):
        self.model_attributes = model_attributes
        self.kwargs = None

    def project(self, df, **kwargs):
        self.kwargs = kwargs
        return df


def test_run_passes_time_periods_base_only_with_nemomod():
    import pandas as pd

    models = _Models(_model_attributes())
    df = pd.DataFrame({"time_period": [0, 1]})
    r = rs.run_combination(models, lambda df_input: df_input, df, "egypt", True, 1, "b", base_year=2017)
    assert r.ok and models.kwargs["time_periods_base"] == [0, 1, 2] and r.base_year == 2017
    rs.run_combination(models, lambda df_input: df_input, df, "egypt", True, 1, "b")
    assert "time_periods_base" not in models.kwargs  # sisepuede's default
    r = rs.run_combination(models, lambda df_input: df_input, df, "egypt", False, 1, "b", base_year=2017)
    assert "time_periods_base" not in models.kwargs and r.base_year is None  # no NemoMod: nothing to fix
