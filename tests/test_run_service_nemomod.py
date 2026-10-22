"""NemoMod status read from sisepuede's log (services/run_service.py): a run
whose electricity model has no solution completes, but is flagged."""

import logging

from sisepuede_tool.models.run_result import RunResult
from sisepuede_tool.services import run_service as rs


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

