"""Excel downloads for the results pages (the pages show charts, not tables).

Every sheet is long format so it filters and pivots easily in Excel:
one row per (year, pathway, ..., value). Pathways are those shown on the page
for the chosen baseline.
"""

import io
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from sisepuede_tool.services import cb_summary_service, emissions_service, results_groups_service


def _xlsx(sheets: Dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
            ws = writer.sheets[name[:31]]
            ws.freeze_panes = "A2"
            for i, col in enumerate(df.columns, start=1):
                width = min(max(len(str(col)), *(len(str(v)) for v in df[col].head(200))) + 2, 60) if len(df) else len(str(col)) + 2
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
    return buf.getvalue()


def emissions_workbook(
    runs: List[Tuple[str, object]],
    baseline_label: str,
    cards: Iterable[dict],
    field_catalog: pd.DataFrame,
) -> bytes:
    """`runs`: [(pathway name, RunResult)] for one baseline. `cards`: every
    driver card (default + custom) to include."""
    by_sub, detail, drivers = [], [], []
    cards = list(cards)
    for name, rr in runs:
        if rr is None or not rr.ok or rr.df_output is None:
            continue
        s = emissions_service.by_subsector(rr.df_output)
        by_sub.append(s.assign(pathway=name, baseline=baseline_label, unit="MtCO2e"))
        d = emissions_service.detail(rr.df_output)
        d = d.groupby(["year", "subsector_abv", "detail", "gas_group", "gas"], as_index=False)["value"].sum()
        d["subsector"] = d["subsector_abv"].map(emissions_service.subsector_label)
        detail.append(d.assign(pathway=name, baseline=baseline_label, unit="MtCO2e"))
        for card in cards:
            f = results_groups_service.card_frame(card, field_catalog, rr)
            if f.empty:
                continue
            drivers.append(
                f.assign(pathway=name, baseline=baseline_label, card=card["title"], source=card["source"], unit=card["unit"])
            )
    cols_sub = ["year", "pathway", "baseline", "sector", "subsector", "unit", "value"]
    cols_det = ["year", "pathway", "baseline", "subsector", "detail", "gas_group", "gas", "unit", "value"]
    cols_drv = ["year", "pathway", "baseline", "card", "series", "source", "unit", "value"]
    df_sub = pd.concat(by_sub)[cols_sub] if by_sub else pd.DataFrame(columns=cols_sub)
    df_det = pd.concat(detail)[cols_det] if detail else pd.DataFrame(columns=cols_det)
    df_drv = pd.concat(drivers)[cols_drv] if drivers else pd.DataFrame(columns=cols_drv)

    dict_rows = []
    for card in cards:
        fields = results_groups_service.card_fields(card, field_catalog)
        meta = field_catalog.set_index("field")
        for r in fields.itertuples():
            dict_rows.append(
                {
                    "card": card["title"],
                    "series": r.series,
                    "field": r.field,
                    "variable": meta.at[r.field, "label"] if r.field in meta.index else r.variable,
                    "subsector": meta.at[r.field, "subsector"] if r.field in meta.index else None,
                    "source": card["source"],
                    "unit_shown": card["unit"],
                    "scale_applied": card["scale"],
                }
            )
    df_dict = pd.DataFrame(dict_rows)
    return _xlsx(
        {
            "emissions_by_subsector": df_sub,
            "emissions_detail": df_det,
            "drivers": df_drv,
            "dictionary": df_dict,
        }
    )


def cb_workbook(long: pd.DataFrame, names: Dict[int, str], baseline_label: str, gdp: Optional[Dict[int, pd.Series]] = None) -> bytes:
    """`long` from cb_summary_service.to_long; `names` {strategy_id: pathway name}."""
    d = long.copy()
    d["pathway"] = d["strategy_id"].map(lambda s: names.get(s, str(s)))
    d["baseline"] = baseline_label
    by_var = d[["year", "pathway", "baseline", "sector_label", "category", "cb_type", "display_name", "variable", "value_busd"]]
    by_var = by_var.rename(columns={"sector_label": "sector", "display_name": "item"})
    by_cat = d.groupby(["year", "pathway", "baseline", "category"], as_index=False)["value_busd"].sum()
    if gdp:
        by_cat["gdp_busd"] = [
            float(gdp[sid].get(y)) if sid in gdp and gdp[sid] is not None and y in gdp[sid].index else None
            for sid, y in zip(d.groupby(["year", "pathway", "baseline", "category"])["strategy_id"].first().values, by_cat["year"])
        ]
        by_cat["pct_gdp"] = by_cat["value_busd"] / by_cat["gdp_busd"] * 100
    items = []
    for sid in sorted(long["strategy_id"].unique()):
        for r in cb_summary_service.DISCOUNT_RATES:
            it = cb_summary_service.items_npv(long, sid, r)
            items.append(it.assign(pathway=names.get(sid, str(sid)), baseline=baseline_label, discount_rate_pct=r))
    npv_items = pd.concat(items) if items else pd.DataFrame()
    if not npv_items.empty:
        npv_items = npv_items.rename(columns={"display_name": "item", "sector_label": "sector", "pv": "net_busd"})[
            ["pathway", "baseline", "discount_rate_pct", "category", "sector", "item", "net_busd"]
        ]
    npv = cb_summary_service.npv_table(long, names)
    npv.insert(1, "baseline", baseline_label)
    notes = pd.DataFrame(
        {
            "note": [
                "Values are billions of USD relative to business as usual: benefits positive, costs negative.",
                f"Totals cover {cb_summary_service.START_YEAR}-2050. discount_rate_pct 0 = not discounted (plain sum), "
                f"which the page shows by default; 3/5/7 discount each year to {cb_summary_service.START_YEAR}.",
                "Costs before 2025 are moved into 2025 by the cost-benefit module.",
            ]
        }
    )
    return _xlsx({"cb_by_variable": by_var, "cb_by_category": by_cat, "totals_by_rate": npv, "items_by_rate": npv_items, "notes": notes})


def article6_workbook(
    runs: List[Tuple[str, pd.DataFrame]],
    baseline_label: str,
    ref: Dict[str, pd.DataFrame],
    price_note: Optional[str] = None,
) -> bytes:
    """`runs`: [(pathway name, article6_service.credit_estimate frame)] for one baseline.
    `ref["prices"]` is the price table used (edited or not); `price_note` says which."""
    cols = ["year", "pathway", "baseline", "emission_group", "emissions_mt", "target_mt", "surplus_mt", "modelled", "credits_mt", "price_usd_per_t", "value_musd"]
    parts = []
    for name, est in runs:
        d = est.rename(
            columns={
                "emission_groups": "emission_group",
                "emissions": "emissions_mt",
                "target": "target_mt",
                "surplus": "surplus_mt",
                "price": "price_usd_per_t",
            }
        )
        parts.append(d.assign(pathway=name, baseline=baseline_label))
    by_group = pd.concat(parts)[cols] if parts else pd.DataFrame(columns=cols)
    totals = (
        by_group.groupby(["year", "pathway", "baseline"], as_index=False)[["emissions_mt", "target_mt", "credits_mt", "value_musd"]].sum()
        if parts
        else pd.DataFrame(columns=["year", "pathway", "baseline", "emissions_mt", "target_mt", "credits_mt", "value_musd"])
    )
    notes = pd.DataFrame(
        {
            "note": [
                "surplus_mt = NDC target - pathway emissions (MtCO2e); positive = below the target.",
                "credits_mt = surplus_mt when positive, else 0; a group above its target does not reduce another group's credits.",
                "modelled = FALSE: the run has no emissions for a group with a target (e.g. electricity without the electricity model); it earns no credits.",
                "value_musd = credits_mt x carbon price (USD per tCO2e = million USD per MtCO2e).",
                "Targets, carbon prices and emission groupings are demo/example values from sisepuede_a6 (sheets below).",
            ]
            + ([price_note] if price_note else [])
        }
    )
    return _xlsx(
        {
            "credits_by_group": by_group,
            "credits_by_year": totals,
            "ndc_targets": ref["targets"],
            "carbon_prices": ref["prices"],
            "emission_groupings": ref["groupings"],
            "notes": notes,
        }
    )
