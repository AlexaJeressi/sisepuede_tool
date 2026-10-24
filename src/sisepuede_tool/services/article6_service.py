"""Article 6 credit estimate, computed by the sisepuede_a6 repository.

The calculation is not done here: credit_estimate() calls
ssp_asix.get_credit_estimate() from a local clone of sisepuede_a6
(https://github.com/jcsyme/sisepuede_a6), so a change to that function changes
the tool's results. The clone is found at $SISEPUEDE_A6_DIR, or next to this
repo (../sisepuede_a6) when the variable is not set.

Reference data, read from the clone's ref/ folder:
- emission_groupings_example.csv: emission_grouping, sisepuede_fields
  ("|"-separated output fields summed into the group);
- ndc_targets_for_a6_demo.csv: year, emission_grouping, target_mt_co2e_ndc2;
- carbon_prices_example.csv: year, price_mm_usd_carbon_per_mt (million USD per
  MtCO2e = USD per tCO2e).
"""

import functools
import importlib.util
import os
import pathlib
from typing import Dict, Iterable, Optional

import pandas as pd
from sisepuede.core.support_classes import TimePeriods

from sisepuede_tool import config

DELIM_SSP_FIELDS = "|"
FIELD_GROUP = "emission_grouping"
FIELD_SSP_FIELDS = "sisepuede_fields"
FIELD_TARGET = "target_mt_co2e_ndc2"
FIELD_PRICE = "price_mm_usd_carbon_per_mt"

# last year of the NDC2.0 targets; the a6 targets after it carry on its NDC run,
# they are not part of the NDC2.0
NDC_LAST_YEAR = 2035

A6_DIR = pathlib.Path(os.environ.get("SISEPUEDE_A6_DIR", config.REPO_ROOT.parent / "sisepuede_a6"))
A6_MODULE_PATH = A6_DIR / "sisepuede_a6" / "src" / "ssp_asix.py"
A6_REF_DIR = A6_DIR / "ref"


@functools.lru_cache(maxsize=1)
def asix():
    """The ssp_asix module of the sisepuede_a6 clone (the repo is not a package,
    so the file is loaded by path)."""
    if not A6_MODULE_PATH.exists():
        raise FileNotFoundError(
            f"sisepuede_a6 not found at {A6_DIR}: clone https://github.com/jcsyme/sisepuede_a6 "
            "next to this repo or set SISEPUEDE_A6_DIR"
        )
    spec = importlib.util.spec_from_file_location("ssp_asix", A6_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@functools.lru_cache(maxsize=1)
def load_reference() -> Dict[str, pd.DataFrame]:
    """{"groupings", "targets", "prices"} from the sisepuede_a6 ref/ folder."""
    return {
        "groupings": pd.read_csv(A6_REF_DIR / "emission_groupings_example.csv"),
        "targets": pd.read_csv(A6_REF_DIR / "ndc_targets_for_a6_demo.csv"),
        "prices": pd.read_csv(A6_REF_DIR / "carbon_prices_example.csv"),
    }


def target_years(targets: pd.DataFrame) -> list:
    return sorted(int(y) for y in targets["year"].unique())


def headline_years(years: Iterable[int]) -> list:
    """The target years put forward on the page (tiles, chart labels): the
    five-year milestones (2030, 2035), or the last year when there is none."""
    years = sorted(int(y) for y in years)
    return [y for y in years if y % 5 == 0] or years[-1:]


@functools.lru_cache(maxsize=4)
def _time_periods(model_attributes) -> TimePeriods:
    return TimePeriods(model_attributes)


def credit_estimate(df_output: pd.DataFrame, model_attributes, ref: Optional[Dict[str, pd.DataFrame]] = None) -> pd.DataFrame:
    """[year, emission_grouping, emissions, target, diff, modelled, price, credits_mt, value_musd].

    value_musd is ssp_asix.get_credit_estimate(). The other columns come from
    the same module, so they follow it: emissions, target and diff (as
    ssp_asix defines it) from get_emissions_from_target_years(), and
    credits_mt from get_credit_estimate_from_diff() at a price of 1.
    modelled = False flags groups with no emissions in the run although they
    have a target (information only; it does not change the credits).
    """
    ref = ref or load_reference()
    m = asix()
    tp = _time_periods(model_attributes)
    groupings, targets, prices = ref["groupings"], ref["targets"], ref["prices"]
    keys = [tp.field_year, m._FIELD_EMISSION_GROUPING]

    diff = m.get_emissions_from_target_years(df_output, groupings, targets, m._FIELD_VALUE_NDC2, model_attributes, tp)
    value = m.get_credit_estimate(df_output, prices, groupings, targets, m._FIELD_VALUE_NDC2, model_attributes, tp)
    tradeable = m.get_credit_estimate_from_diff(diff, prices.assign(**{m._FIELD_PRICE_CARBON: 1.0}), tp)

    df = (
        diff.rename(columns={"emission_total_co2e": "emissions", m._FIELD_VALUE_NDC2: "target", m._FIELD_EMISSION_DIFF: "diff"})
        .merge(prices.rename(columns={m._FIELD_PRICE_CARBON: "price"})[[tp.field_year, "price"]], on=tp.field_year, how="left")
        .merge(tradeable.rename(columns={m._FIELD_CREDIT_VALUE: "credits_mt"}), on=keys, how="left")
        .merge(value.rename(columns={m._FIELD_CREDIT_VALUE: "value_musd"}), on=keys, how="left")
        .rename(columns={tp.field_year: "year"})
    )
    # a group without a target (NaN) has no credits
    df[["credits_mt", "value_musd"]] = df[["credits_mt", "value_musd"]].fillna(0.0)
    df["modelled"] = (df["emissions"] != 0) | (df["target"].fillna(0) == 0)
    return df[["year", FIELD_GROUP, "emissions", "target", "diff", "modelled", "price", "credits_mt", "value_musd"]]


def _target_groups(targets: pd.DataFrame) -> list:
    """Emission groups with an NDC target (a group whose target is NaN earns no credits)."""
    return sorted(targets.loc[targets[FIELD_TARGET].notna(), FIELD_GROUP].unique())


def emissions_by_year(df_output: pd.DataFrame, model_attributes, ref: Optional[Dict[str, pd.DataFrame]] = None) -> pd.Series:
    """Emissions (MtCO2e) by year, every year of the run, summed over the
    emission groups that have an NDC target: the emissions the credits compare
    with the targets, summed by ssp_asix.get_emissions_from_target_years()
    (asked for every year, with a dummy target)."""
    ref = ref or load_reference()
    m = asix()
    tp = _time_periods(model_attributes)
    years = sorted(tp.tps_to_years(df_output[[tp.field_time_period]])[tp.field_year].unique())
    every_year = pd.DataFrame(
        [(y, g, 0.0) for y in years for g in _target_groups(ref["targets"])],
        columns=[tp.field_year, FIELD_GROUP, m._FIELD_VALUE_NDC2],
    )
    em = m.get_emissions_from_target_years(df_output, ref["groupings"], every_year, m._FIELD_VALUE_NDC2, model_attributes, tp)
    out = em.groupby(tp.field_year)["emission_total_co2e"].sum()
    out.index = out.index.astype(int)
    return out


def price_by_year(prices: pd.DataFrame, years) -> Dict[int, float]:
    """{year: carbon price (USD/tCO2e)} for `years` (NaN when the table has no price)."""
    p = prices.set_index("year")[FIELD_PRICE]
    return {int(y): float(p.get(y, float("nan"))) for y in years}


def with_prices(prices: pd.DataFrame, overrides: Dict[int, float]) -> pd.DataFrame:
    """Copy of the carbon price table with the prices of some years replaced
    (years not in the table are added)."""
    out = prices.copy()
    for year, price in overrides.items():
        if (out["year"] == year).any():
            out.loc[out["year"] == year, FIELD_PRICE] = float(price)
        else:
            out = pd.concat([out, pd.DataFrame({"year": [year], FIELD_PRICE: [float(price)]})], ignore_index=True)
    return out.sort_values("year").reset_index(drop=True)


def not_modelled(est: pd.DataFrame) -> list:
    """Emission groups with a target but no emissions in the run."""
    return sorted(est.loc[~est["modelled"].astype(bool), FIELD_GROUP].unique())


def totals_by_year(est: pd.DataFrame) -> pd.DataFrame:
    """[year, emissions, target, credits_mt, value_musd, price] summed over groups."""
    out = est.groupby("year", as_index=False)[["emissions", "target", "credits_mt", "value_musd"]].sum()
    out["price"] = out["year"].map(est.groupby("year")["price"].first())
    return out


def earns_credits(codes: Iterable[str], ndc_codes: Iterable[str]) -> bool:
    """Whether a pathway can earn Article 6 credits: the NDC targets are the
    NDC pathway's own emissions, so only action beyond the NDC counts. A pathway
    with no transformations (business as usual) or with NDC transformations
    only is the reference, not a source of credits."""
    codes = set(codes)
    return bool(codes - set(ndc_codes))


def group_colors(groupings: pd.DataFrame, subsector_colors: Dict[str, str]) -> Dict[str, str]:
    """{emission group: colour} from the subsector of the group's first field
    (e.g. emission_co2e_subsector_total_trns -> trns)."""
    out = {}
    for g in groupings.itertuples(index=False):
        first = str(getattr(g, FIELD_SSP_FIELDS)).split(DELIM_SSP_FIELDS)[0]
        abv = first.rsplit("_", 1)[-1]
        if abv in subsector_colors:
            out[str(getattr(g, FIELD_GROUP))] = subsector_colors[abv]
    return out
