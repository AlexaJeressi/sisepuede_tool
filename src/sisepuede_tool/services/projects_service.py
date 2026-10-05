"""Candidate projects from the shipped Egypt NDC/LTS project list
(src/sisepuede_tool/ref/Egypt_Projects_SISEPUEDE_NDC_LTS.xlsx), and their
links to transformations.

The list is read live from that file, not hardcoded, so edits to the
workbook are picked up on the next app start. Each row names the SISEPUEDE
transformer it maps to (`transformer_code`), and row N corresponds to the
NDC news transformation `..._NEWS_N` in resources/library/egypt_ndc_news
(same project name), which is the default link.

Links are session state (`project -> transformation code`), saved with the
project as project_links.csv. Users can also add their own projects
(custom_projects.csv).
"""

import functools
import pathlib
import re
from typing import Dict, Iterable, List, Optional, Union

import pandas as pd

DISPLAY_COLUMNS = ["Project Name", "Project Description", "Total Investment (Estimated)", "Status", "NDC Notes"]

# workbook columns kept for the Projects page (renamed to snake_case)
_COLUMNS = {
    "Project Name": "name",
    "Subsector": "subsector",
    "transformer_code": "transformer_code",
    "Project Description": "description",
    "Total Investment (Estimated)": "investment",
    "Link(s)": "links",
    "Start Year / Duration": "start",
    "Status": "status",
    "Duplicate / Overlap Note": "overlap_note",
    "NDC": "ndc",
    "NDC Notes": "ndc_notes",
    "LTS": "lts",
    "LTS Notes": "lts_notes",
}
PROJECT_COLUMNS = list(_COLUMNS.values()) + ["news_number", "source"]

SOURCE_WORKBOOK = "workbook"
SOURCE_CUSTOM = "custom"


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


def load_project_records(path: Union[str, pathlib.Path]) -> pd.DataFrame:
    """All Projects-page columns, one row per project, with `news_number`
    (the workbook row number, 1-based) and `source`."""
    raw = pd.read_excel(path, sheet_name=0)
    raw["news_number"] = range(1, len(raw) + 1)
    df = raw[[c for c in _COLUMNS if c in raw.columns] + ["news_number"]].rename(columns=_COLUMNS)
    for col in _COLUMNS.values():
        if col not in df.columns:
            df[col] = None
    df = df.dropna(subset=["name"])
    df["name"] = df["name"].astype(str).str.strip()
    df = df.drop_duplicates(subset=["name"], keep="first")
    df = df.astype(object).where(pd.notna(df), None)
    df["source"] = SOURCE_WORKBOOK
    return df[PROJECT_COLUMNS].reset_index(drop=True)


@functools.lru_cache(maxsize=1)
def load_project_records_cached(path: Union[str, pathlib.Path]) -> pd.DataFrame:
    return load_project_records(path)


def ndc_flag(value: Optional[str]) -> str:
    """'Yes — measure' / 'Yes — named' -> 'yes'; 'Partial' -> 'partial'; else 'no'."""
    v = (value or "").strip().lower()
    if v.startswith("yes"):
        return "yes"
    if v.startswith("partial"):
        return "partial"
    return "no"


def split_links(value: Optional[str]) -> List[str]:
    return [u.strip() for u in re.split(r"\s*\|\s*", value or "") if u.strip()]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def default_links(projects: pd.DataFrame, library_items: Iterable) -> Dict[str, Optional[str]]:
    """project name -> NDC news transformation code, matched by project name
    (the news item's name is 'NEWS_NN - <project name>'), falling back to the
    workbook row number. Items that can't be used with the installed
    sisepuede are not linked."""
    items = [i for i in library_items if getattr(i, "ok", True)]
    by_name = {}
    by_number = {}
    for item in items:
        name = item.name.split(" - ", 1)[1] if " - " in item.name else item.name
        by_name[_norm(name)] = item.code
        if item.news_number is not None:
            by_number[item.news_number] = item.code
    links: Dict[str, Optional[str]] = {}
    for rec in projects.to_dict("records"):
        code = by_name.get(_norm(rec["name"]))
        if code is None and rec.get("news_number") is not None:
            code = by_number.get(int(rec["news_number"]))
        links[rec["name"]] = code
    return links


def make_custom_project(
    name: str,
    transformer_code: Optional[str] = None,
    description: str = "",
    investment: str = "",
    status: str = "",
    start: str = "",
    ndc: str = "No",
) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("A project needs a name.")
    rec = {col: None for col in PROJECT_COLUMNS}
    rec.update(
        {
            "name": name,
            "subsector": transformer_code.split(":")[1] if transformer_code and transformer_code.count(":") >= 2 else None,
            "transformer_code": transformer_code or None,
            "description": description or None,
            "investment": investment or None,
            "status": status or None,
            "start": start or None,
            "ndc": ndc or None,
            "source": SOURCE_CUSTOM,
        }
    )
    return rec


def all_projects(workbook: pd.DataFrame, custom: List[dict]) -> pd.DataFrame:
    if not custom:
        return workbook
    return pd.concat([workbook, pd.DataFrame(custom, columns=PROJECT_COLUMNS)], ignore_index=True)


def links_to_dataframe(links: Dict[str, Optional[str]], in_scope: Dict[str, bool]) -> pd.DataFrame:
    names = sorted(set(links) | set(in_scope))
    return pd.DataFrame(
        {
            "project": names,
            "transformation_code": [links.get(n) or "" for n in names],
            "in_scope": [bool(in_scope.get(n, False)) for n in names],
        }
    )


def links_from_dataframe(df: pd.DataFrame):
    links, in_scope = {}, {}
    for rec in df.to_dict("records"):
        name = str(rec["project"])
        code = rec.get("transformation_code")
        links[name] = code if isinstance(code, str) and code else None
        in_scope[name] = str(rec.get("in_scope")).lower() in ("true", "1")
    return links, in_scope


def projects_for_transformation(code: str, links: Dict[str, Optional[str]]) -> List[str]:
    return [name for name, linked in links.items() if linked == code]
