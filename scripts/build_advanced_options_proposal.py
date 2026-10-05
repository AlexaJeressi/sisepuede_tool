"""Write docs/advanced_options_proposal.md: which parameters each transformer
shows in basic mode and which only under Advanced options.

Uses the same specs as the editor (widget_metadata.build_param_specs, with
resources/param_schemas.yaml and transformer_widget_metadata.yaml), so the
doc follows any change to those files. Run:

    python scripts/build_advanced_options_proposal.py [baseline.csv]
"""

import datetime
import pathlib
import sys
from collections import defaultdict

import pandas as pd

from sisepuede_tool.models.param_spec import WidgetKind
from sisepuede_tool.services import catalog_service, labels, transformer_metadata_service, widget_metadata

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "tests" / "fixtures" / "egypt_baseline_biomass_fix.csv"
OUT = ROOT / "docs" / "advanced_options_proposal.md"


def _describe(spec) -> str:
    text = f"`{spec.name}` ({labels.param_label(spec.name, spec.label)})"
    if spec.kind == WidgetKind.DICT_TABLE:
        rule = (spec.schema or {}).get("sum_rule")
        text += " — table" + {"eq1": ", must total 100%", "leq1": ", at most 100%"}.get(rule, "")
    elif spec.kind == WidgetKind.NOTE:
        text += " — note only"
    return text


def main(csv_path=DEFAULT_CSV) -> None:
    ma = catalog_service.build_model_attributes()
    tk = catalog_service.build_transformers_catalog(pd.read_csv(csv_path))
    catalog = transformer_metadata_service.load_catalog()
    overrides = widget_metadata.load_overrides(widget_metadata.default_overrides_path())

    by_sector = defaultdict(list)
    no_basic = []
    for code in tk.all_tkernels_non_baseline:
        card = transformer_metadata_service.get_card(code, catalog)
        specs = widget_metadata.build_param_specs(tk.get_tkernel(code), ma, tk, overrides)
        main = card.get("magnitude_param")
        basic, advanced = [], []
        for spec in specs:
            if spec.kind == WidgetKind.RAMP_VECTOR:
                continue
            is_main = spec.name == main and spec.kind == WidgetKind.NUMERIC
            (basic if spec.tier == "basic" or is_main else advanced).append(_describe(spec))
        if not basic:
            no_basic.append(code)
        flag = " ⚠" if not basic else ""
        by_sector[card.get("sector") or "other"].append(
            f"| `{code}`<br>{card['name']}{flag} | {card.get('status') or ''} | "
            f"{'<br>'.join(basic) or '—'} + ramp | {'<br>'.join(advanced) or '—'} |"
        )

    lines = [
        "# Proposed basic / advanced parameters per transformer",
        "",
        f"Generated {datetime.date.today()} by `scripts/build_advanced_options_proposal.py` from the editor's specs.",
        "Rules: main magnitude + implementation ramp = basic; guided tables from "
        "`resources/param_schemas.yaml` use their own `tier`; everything else = advanced; `return_*` hidden.",
        "Change a parameter's tier with `tier:` in `param_schemas.yaml` or "
        "`resources/transformer_widget_metadata.yaml`.",
        "",
        "⚠ = nothing but the ramp in basic mode.",
        "",
    ]
    for sector in sorted(by_sector):
        lines += [f"## {sector}", "", "| Transformer | Status | Basic | Advanced |", "|---|---|---|---|"]
        lines += by_sector[sector] + [""]
    lines += ["## Transformers with nothing but the ramp in basic mode", ""]
    lines += [f"- `{c}`" for c in no_basic] or ["- none"]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(no_basic)} without a basic input)")


if __name__ == "__main__":
    main(*sys.argv[1:])
