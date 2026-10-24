"""Rebuild the Jobs page's data (src/sisepuede_tool/resources/jobs/data) from
new SISEPUEDE runs.

    python scripts/build_jobs_data.py --cb-data path/to/cb_data.csv

cb_data.csv: the pathways' costs and benefits, as the tool's Tableau download
(Results > Cost & benefits) or ssp_egypt's ssp_modeling/tableau/data/tool_pathways
write it. The process is the one of the Egypt deck's jobs slides
(services/jobs_service.py, resources/jobs/README.md). The input-output results,
population and employment shares are the ones in resources/jobs/inputs;
--inputs points to another folder with the same three files.

--pathway CODE=NAME (repeatable) names a pathway of cb_data (strategy_code) in
the jobs tables; the default takes PFLO:NDC and PFLO:NDC2_0 as NDC and PFLO:LEP
as LEP, the low emissions pathway the baseline labour market is changed by.
"""

import argparse
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from sisepuede_tool.services import jobs_service as js  # noqa: E402


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cb-data", required=True, type=pathlib.Path, help="cb_data.csv of the runs")
    p.add_argument("--inputs", type=pathlib.Path, default=js.INPUTS_DIR, help=f"input folder (default {js.INPUTS_DIR})")
    p.add_argument("--out", type=pathlib.Path, default=js.DATA_DIR, help=f"output folder (default {js.DATA_DIR})")
    p.add_argument("--pathway", action="append", default=[], metavar="CODE=NAME", help="cb_data strategy_code -> pathway name")
    args = p.parse_args(argv)

    pathways = dict(js.PATHWAYS)
    for item in args.pathway:
        code, _, name = item.partition("=")
        if not name:
            p.error(f"--pathway {item!r}: expected CODE=NAME")
        pathways[code] = name

    cb = pd.read_csv(args.cb_data)
    found = sorted(set(cb["strategy_code"]) & set(pathways))
    if not found:
        p.error(f"no pathway of {sorted(pathways)} in {args.cb_data} (strategy_code: {sorted(set(cb['strategy_code']))})")
    tables = js.build(cb, args.inputs, pathways)
    if js.LOW_EMISSIONS not in set(tables["technical_cost"]["Pathway"]):
        p.error(f"no {js.LOW_EMISSIONS} pathway in {args.cb_data}: the baseline labour market needs it")
    js.write(tables, args.out)
    for key, f in js.FILES.items():
        print(f"{args.out / f}: {len(tables[key])} rows")


if __name__ == "__main__":
    main()
