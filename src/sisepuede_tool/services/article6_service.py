"""Article 6 credit estimate: mitigation beyond the NDC target, valued at a carbon price.

Ported from sisepuede_a6 (sisepuede_a6/src/ssp_asix.py), without the
ModelAttributes / TimePeriods dependency. For each NDC target year and each
emission group:

    surplus = NDC target - pathway emissions        (MtCO2e)
    credits = max(surplus, 0)                        (tradeable MtCO2e)
    value   = credits * carbon price                 (million USD)

A positive surplus means the pathway emits less than the target. A shortfall
in one group does not reduce the credits from another (groups are clipped
one by one, as in ssp_asix). A group whose emissions are exactly zero while
its target is not (e.g. electricity and fugitive emissions in a run without
the electricity model) is marked not modelled and earns no credits. Note: ssp_asix computes result - target and
clips that, which would credit emitting *above* the target; the sign is
flipped here so the result matches its own docstring.

Reference data (resources/article6/, copied from sisepuede_a6/ref):
- emission_groupings.csv: emission_groups, sisepuede_fields ("|"-separated
  output fields summed into the group);
- ndc_targets.csv: year, emission_groups, target_mt_co2e_ndc2 (demo targets);
- carbon_prices.csv: year, price_mm_usd_carbon_per_mt (million USD per
  MtCO2e = USD per tCO2e; example prices).
"""

import functools
import pathlib
from typing import Dict, Iterable, Optional

import pandas as pd

import sisepuede_tool
from sisepuede_tool.services.emissions_service import YEAR_0

DELIM_SSP_FIELDS = "|"
FIELD_GROUP = "emission_groups"
FIELD_SSP_FIELDS = "sisepuede_fields"
FIELD_TARGET = "target_mt_co2e_ndc2"
FIELD_PRICE = "price_mm_usd_carbon_per_mt"

RESOURCES_DIR = pathlib.Path(sisepuede_tool.__file__).parent / "resources" / "article6"


@functools.lru_cache(maxsize=1)
def load_reference() -> Dict[str, pd.DataFrame]:
    """{"groupings", "targets", "prices"} from resources/article6/."""
    return {
        "groupings": pd.read_csv(RESOURCES_DIR / "emission_groupings.csv"),
        "targets": pd.read_csv(RESOURCES_DIR / "ndc_targets.csv"),
        "prices": pd.read_csv(RESOURCES_DIR / "carbon_prices.csv"),
    }


def target_years(targets: pd.DataFrame) -> list:
    return sorted(int(y) for y in targets["year"].unique())


def emissions_vs_targets(df_output: pd.DataFrame, groupings: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """[year, emission_groups, emissions, target, surplus, modelled] (MtCO2e) for the target years.

    surplus = target - emissions: positive = beyond the NDC target.
    modelled = False when the run has no emissions for a group that has a target.
    """
    years = df_output["time_period"].astype(int) + YEAR_0
    rows = df_output[years.isin(targets["year"]).values]
    yrs = (rows["time_period"].astype(int) + YEAR_0).values
    parts = []
    for g in groupings.itertuples(index=False):
        group = str(getattr(g, FIELD_GROUP))
        fields = [f for f in str(getattr(g, FIELD_SSP_FIELDS)).split(DELIM_SSP_FIELDS) if f in rows.columns]
        parts.append(pd.DataFrame({"year": yrs, FIELD_GROUP: group, "emissions": rows[fields].sum(axis=1).values}))
    if not parts:
        return pd.DataFrame(columns=["year", FIELD_GROUP, "emissions", "target", "surplus", "modelled"])
    df = pd.concat(parts, ignore_index=True).merge(
        targets.rename(columns={FIELD_TARGET: "target"})[["year", FIELD_GROUP, "target"]],
        on=["year", FIELD_GROUP],
        how="inner",
    )
    df["surplus"] = df["target"] - df["emissions"]
    df["modelled"] = (df["emissions"] != 0) | (df["target"] == 0)
    return df


def credits(df_diff: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Adds price (USD/tCO2e), credits_mt (tradeable MtCO2e) and value_musd (million USD)."""
    df = df_diff.merge(prices.rename(columns={FIELD_PRICE: "price"})[["year", "price"]], on="year", how="left")
    df["credits_mt"] = df["surplus"].clip(lower=0).where(df["modelled"], 0.0)
    df["value_musd"] = df["credits_mt"] * df["price"]
    return df


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


def credit_estimate(df_output: pd.DataFrame, ref: Optional[Dict[str, pd.DataFrame]] = None) -> pd.DataFrame:
    """[year, emission_groups, emissions, target, surplus, modelled, price, credits_mt, value_musd]."""
    ref = ref or load_reference()
    return credits(emissions_vs_targets(df_output, ref["groupings"], ref["targets"]), ref["prices"])


def not_modelled(est: pd.DataFrame) -> list:
    """Emission groups left out of the credits because the run has no emissions for them."""
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
