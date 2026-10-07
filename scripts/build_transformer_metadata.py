"""Build resources/transformer_catalog.yaml: top variables and emissions
direction per transformer, for the Pathways page.

Runs every transformer with its default parameters against a baseline, then
projects the result without the electricity model (no Julia), so it takes a
couple of minutes. Curated blocks already in the YAML are kept.

Usage (from the repo root, in ssp_biomass_env):
    python scripts/build_transformer_metadata.py
    python scripts/build_transformer_metadata.py --baseline path/to.csv --no-emissions
    python scripts/build_transformer_metadata.py --only TFR:AGRC:DEC_CH4_RICE TFR:LVST:INC_PRODUCTIVITY
"""

import argparse
import datetime
import json
import logging
import pathlib
import sys
import time
import warnings

import pandas as pd

from sisepuede_tool import config
from sisepuede_tool.services import catalog_service
from sisepuede_tool.services import transformer_metadata_service as tms

DEFAULT_BASELINE = config.REPO_ROOT / "tests" / "fixtures" / "example_input.csv"


def _sisepuede_version() -> str:
    """Installed sisepuede commit (from pip's direct_url.json), if any."""
    try:
        from importlib.metadata import distribution

        dist = distribution("sisepuede")
        direct = dist.read_text("direct_url.json")
        if direct:
            info = json.loads(direct)
            commit = (info.get("vcs_info") or {}).get("commit_id")
            if commit:
                return f"{dist.version}@{commit[:7]}"
        return dist.version
    except Exception:
        return "unknown"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", type=pathlib.Path, default=DEFAULT_BASELINE)
    parser.add_argument("--out", type=pathlib.Path, default=tms.default_catalog_path())
    parser.add_argument("--no-emissions", action="store_true", help="skip the model runs (variables only)")
    parser.add_argument("--only", nargs="+", help="transformer codes to (re)compute; others are kept as-is")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    warnings.filterwarnings("ignore")
    log = logging.getLogger("build_transformer_metadata")

    df = pd.read_csv(args.baseline)
    regions = sorted(df["region"].unique().tolist()) if "region" in df.columns else None
    log.info("baseline %s: %s rows, %s columns, regions %s", args.baseline.name, *df.shape, regions)

    t0 = time.time()
    tk = catalog_service.build_transformers_catalog(df)
    ma = tk.model_attributes
    log.info("TransformerKernels built in %.1fs (%d transformers)", time.time() - t0, len(tk.all_tkernels_non_baseline))

    models = df_out_baseline = None
    if not args.no_emissions:
        from sisepuede.manager.sisepuede_models import SISEPUEDEModels

        models = SISEPUEDEModels(ma, allow_electricity_run=False, initialize_julia=False)
        df_out_baseline = models.project(tk.baseline(), include_nemo_fuel_production=False, regions=regions)
        log.info("baseline projection done")

    existing = tms.load_catalog(args.out)
    codes = args.only or list(tk.all_tkernels_non_baseline)
    computed = {code: (existing.get("transformers", {}).get(code) or {}).get("computed") for code in tk.all_tkernels_non_baseline}
    computed = {c: v for c, v in computed.items() if v is not None}

    for i, code in enumerate(codes, 1):
        t = time.time()
        entry = tms.build_entry(tk, code, models=models, df_out_baseline=df_out_baseline, regions=regions)
        computed[code] = entry
        emis = (entry.get("emissions_alone") or {}).get("direction")
        log.info("[%2d/%d] %-45s %-22s emissions=%-24s %.1fs", i, len(codes), code, entry.get("status"), emis, time.time() - t)

    # the library transformations (NDC, LEP) with their own parameters: a
    # transformer's default can differ in sign from the version used in a pathway
    library = None
    if not args.no_emissions:
        from sisepuede_tool.services import library_service

        items = library_service.load_all_libraries()
        built = library_service.build_library_transformations(items, tk)
        library = {}
        for i, (code, transformation) in enumerate(built.items(), 1):
            t = time.time()
            library[code] = tms.build_library_entry(tk, transformation, models, df_out_baseline, regions=regions)
            emis = (library[code].get("emissions_alone") or {}).get("direction")
            log.info("[library %2d/%d] %-55s emissions=%-24s %.1fs", i, len(built), code, emis, time.time() - t)

    meta = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "sisepuede": _sisepuede_version(),
        "baseline": args.baseline.name,
        "regions": regions,
        "emissions_year": int(ma.get_dimensional_attribute_table(ma.dim_time_period).table["year"].max()),
        "emissions_computed": not args.no_emissions,
        "emissions_units": "MtCO2e",
        "notes": "Transformers at default parameters; `library`: the shipped NDC/LEP transformations with "
        "their own parameters. Emissions without the electricity model (NemoMod).",
    }
    catalog = tms.merge_catalog(computed, existing, meta, library=library)
    tms.save_catalog(catalog, args.out)

    statuses = pd.Series([e["computed"].get("status") for e in catalog["transformers"].values()]).value_counts()
    log.info("wrote %s\n%s", args.out, statuses.to_string())
    for code, e in catalog["transformers"].items():
        if e["computed"].get("status") == "error":
            log.warning("ERROR %s: %s", code, e["computed"].get("error"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
