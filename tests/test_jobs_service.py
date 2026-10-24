"""Jobs (services/jobs_service.py): the process reproduces the shipped tables
(resources/jobs/data, from the Egypt deck's Tableau workbook and R scripts)."""

import numpy as np
import pandas as pd
import pytest

from sisepuede_tool.services import jobs_service as js


def _same(a: pd.DataFrame, b: pd.DataFrame, keys, rtol=1e-9):
    a = a.sort_values(keys).reset_index(drop=True)
    b = b.sort_values(keys).reset_index(drop=True)
    assert list(a.columns) == list(b.columns) and len(a) == len(b)
    num = a.select_dtypes("number").columns
    pd.testing.assert_frame_equal(a.drop(columns=num).astype(str), b.drop(columns=num).astype(str))
    np.testing.assert_allclose(b[num].to_numpy(float), a[num].to_numpy(float), rtol=rtol, atol=1e-9)


@pytest.fixture(scope="module")
def shipped():
    return js.load.__wrapped__(js.DATA_DIR)


def test_jobs_demand_and_multiplier_from_the_io_results(shipped):
    demand = js.jobs_demand(pd.read_csv(js.INPUTS_DIR / js.IO_RESULTS))
    got = demand.reset_index().rename(columns={"index": "Unnamed: 0"})
    _same(shipped["jobs_demand"], got, ["Unnamed: 0"])
    # the sum over a sector's transformations: 27.28 jobs per million USD in construction for buildings
    mult = js.multiplier(demand)
    _same(shipped["multiplier"], mult, ["Economic Sector", "Ssp Sector"])
    assert mult.set_index(["Economic Sector", "Ssp Sector"]).loc[("Construction", "Buildings"), "Total Jobs"] == pytest.approx(27.2822)


def test_jobs_over_time_from_the_multiplier_and_investments(shipped):
    detail = js.direct_jobs(shipped["multiplier"], shipped["technical_cost"])
    _same(shipped["direct_detail"], detail, ["Sector", "Ssp.Sector", "Economic.Sector", "Pathway", "Year"])
    direct = js.direct_jobs_by_sector(detail)
    _same(shipped["direct"], direct, ["Economic.Sector", "Pathway", "Year"])
    population = pd.read_csv(js.INPUTS_DIR / js.POPULATION)
    base = js.baseline_jobs(population, pd.read_csv(js.INPUTS_DIR / js.SECTOR_SHARES))
    total = js.jobs_overtime(base, direct, population)
    _same(shipped["total"], total, ["Economic.Sector", "Year", "Pathway"])
    # reallocation keeps the baseline's total; expansion adds the LEP's jobs
    by = total.groupby(["Pathway", "Year"])["Jobs"].sum().unstack(0)
    assert by.loc[2050, js.REALLOCATION] == pytest.approx(by.loc[2050, js.BASELINE])
    assert by.loc[2050, js.EXPANSIONARY] - by.loc[2050, js.BASELINE] == pytest.approx(
        direct.query("Pathway == 'LEP' and Year == 2050")["Total.Jobs"].sum())


def test_technical_cost_from_cb_data():
    cb = pd.DataFrame({
        "strategy_code": ["PFLO:LEP", "PFLO:LEP", "PFLO:LEP", "PFLO:LEP", "PFLO:NDC2_0", "PFLO:LEP", "BASE"],
        "sector": ["entc", "entc", "soil", "entc", "trns", "entc", "entc"],
        "cb_type": ["technical_cost", "technical_cost", "technical_cost", "fuel_cost", "technical_cost", "technical_cost", "technical_cost"],
        "Year": [2030, 2030, 2030, 2030, 2040, 2022, 2030],
        "value": [-1.0, -0.5, -9.0, -7.0, 0.0, -3.0, -5.0],
    })
    t = js.technical_cost(cb)
    # capex + opex, signs flipped; soil, other types, years before 2023 and BAU left out; zeros kept
    assert t.to_dict("records") == [
        {"Pathway": "LEP", "Year1": 2030, "Sector": "EN - Power Industry (entc)", "Investments": 1.5},
        {"Pathway": "NDC", "Year1": 2040, "Sector": "EN - Transportation", "Investments": 0.0},
    ]


def test_build_and_write_round_trip(tmp_path, shipped):
    # the shipped investments as cb_data rows: build() gives back the shipped tables
    inv = shipped["technical_cost"]
    sector = {v: k for k, v in js.COST_SECTORS.items()}
    cb = pd.DataFrame({"strategy_code": "PFLO:" + inv["Pathway"], "sector": inv["Sector"].map(sector),
                       "cb_type": "technical_cost", "Year": inv["Year1"], "value": -inv["Investments"]})
    tables = js.build(cb)
    js.write(tables, tmp_path)
    back = js.load.__wrapped__(tmp_path)
    _same(shipped["total"], back["total"], ["Economic.Sector", "Year", "Pathway"])
    _same(shipped["direct"], back["direct"], ["Economic.Sector", "Pathway", "Year"])
