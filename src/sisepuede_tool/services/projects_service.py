"""Loading candidate project records from the shipped Egypt NDC/LTS project
list (src/sisepuede_tool/ref/Egypt_Projects_SISEPUEDE_NDC_LTS.xlsx).

The project list is read live from that file, not hardcoded, so edits to
the workbook are picked up on the next app start without any code change.
Only the columns the Projects page actually shows are kept; the workbook
also carries Subsector/Transformation Code/NDC/LTS columns tying each
project back to a SISEPUEDE transformer, which aren't surfaced yet.
"""

import functools
import pathlib
from typing import Union

import pandas as pd

DISPLAY_COLUMNS = ["Project Name", "Project Description", "Total Investment (Estimated)", "Status", "NDC Notes"]


def load_projects(path: Union[str, pathlib.Path]) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0)
    missing = [c for c in DISPLAY_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Projects workbook is missing expected column(s): {missing}")

    df = df[DISPLAY_COLUMNS].copy()
    df = df.dropna(subset=["Project Name"])
    df["Project Name"] = df["Project Name"].astype(str).str.strip()
    df = df.drop_duplicates(subset=["Project Name"], keep="first")
    return df.reset_index(drop=True)


@functools.lru_cache(maxsize=1)
def load_projects_cached(path: Union[str, pathlib.Path]) -> pd.DataFrame:
    return load_projects(path)
