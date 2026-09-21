"""Export/import Transformations + Strategies to/from sisepuede-native
project files (config_general.yaml, transformation_*.yaml,
strategy_definitions.csv, citations.bib), for reuse in the CLI, notebooks,
or other sisepuede-based tools. Verified against a real example directory
(ssp_egypt/ssp_modeling/transformations) -- same filenames, same YAML
schema, same strategy_definitions.csv columns and "|" delimiter.

Two entry points, both built on the same directory-based core:

- The Save/Load tab works with a single in-memory .zip for browser
  download/upload (export_session_zip / import_session_zip), since it's
  meant to move a whole project between machines/sessions.
- The Transformations tab's Save/Load buttons work with a real directory
  path on the local filesystem directly (export_transformations_dir /
  import_transformations_dir) -- this app is local single-user, so reading
  and writing a path the user names is the natural fit, no browser
  upload/download round-trip needed.

Both are explicit, user-triggered actions -- state is otherwise session-only
in memory (see the plan's Persistence section). Import wraps the existing
`Transformations(dir, transformer_kernels=...)` directory constructor (read-only at
construction) -- `strategy_definitions.csv` is hand-parsed into bare
`Strategy` objects rather than instantiating the `Strategies` collection,
which has real file-system write side effects on construction.
"""

import io
import pathlib
import re
import tempfile
import zipfile
from typing import Dict, Tuple, Union

import pandas as pd
import yaml
import sisepuede.transformers as trf

from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import strategy_service

STRATEGY_DEFINITIONS_FILENAME = "strategy_definitions.csv"
CONFIG_GENERAL_FILENAME = "config_general.yaml"
CITATIONS_FILENAME = "citations.bib"

PathLike = Union[str, pathlib.Path]


def _slug(code: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", code.lower()).strip("_")


def _to_yaml_safe(obj):
    """yaml.safe_dump has no representer for tuples (e.g. window_logistic);
    recursively convert to plain lists/dicts so export never raises."""
    if isinstance(obj, dict):
        return {k: _to_yaml_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_yaml_safe(v) for v in obj]
    return obj


def _transformation_to_config(transformation: trf.Transformation) -> dict:
    return {
        "citations": transformation.citations,
        "description": transformation.description,
        "identifiers": {
            "transformation_code": transformation.code,
            "transformation_name": transformation.name,
        },
        "parameters": _to_yaml_safe(transformation.dict_parameters),
        "transformer": transformation.transformer_code,
    }


def strategies_to_dataframe(strategies_map: Dict[int, StrategyEntry]) -> pd.DataFrame:
    rows = [
        {
            "strategy_id": entry.strategy.id_num,
            "strategy_code": entry.strategy.code or "",
            "strategy": entry.strategy.name or "",
            "description": getattr(entry.strategy, "description", "") or "",
            "transformation_specification": "|".join(entry.transformation_codes),
        }
        for entry in strategies_map.values()
    ]
    return pd.DataFrame(
        rows, columns=["strategy_id", "strategy_code", "strategy", "description", "transformation_specification"]
    )


def _parse_strategy_definitions(fp_csv: pathlib.Path, transformations_obj: trf.Transformations) -> Dict[int, StrategyEntry]:
    strategies_map: Dict[int, StrategyEntry] = {}
    if not fp_csv.exists():
        return strategies_map

    df = pd.read_csv(fp_csv)
    for _, row in df.iterrows():
        strategy_id = int(row["strategy_id"])
        codes = [c for c in str(row["transformation_specification"]).split("|") if c]

        if strategy_id == 0:
            strategy = strategy_service.build_baseline_strategy(transformations_obj)
            codes = [transformations_obj.code_baseline]
        else:
            name = str(row.get("strategy") or f"Strategy {strategy_id}")
            description = str(row.get("description") or "")
            strategy = strategy_service.build_strategy(
                strategy_id, codes, transformations_obj, name=name, description=description
            )

        strategies_map[strategy_id] = StrategyEntry(strategy=strategy, transformation_codes=codes)

    return strategies_map


def export_transformations_dir(
    transformations_obj: trf.Transformations,
    strategies_map: Dict[int, StrategyEntry],
    dir_path: PathLike,
) -> None:
    """Write config_general.yaml, one transformation_<code>.yaml per
    non-baseline Transformation, strategy_definitions.csv, and an (empty,
    unless one already exists) citations.bib into `dir_path` -- creating it
    if it doesn't exist. Loadable unmodified by
    Transformations(dir_path, transformer_kernels=...) / the sisepuede CLI, and
    matches the shape of a real hand-built transformations directory."""
    dir_path = pathlib.Path(dir_path)
    dir_path.mkdir(parents=True, exist_ok=True)

    fp_general = transformations_obj.dict_paths.get(transformations_obj.key_path_config_general)
    (dir_path / CONFIG_GENERAL_FILENAME).write_bytes(pathlib.Path(fp_general).read_bytes())

    for code, transformation in transformations_obj.dict_transformations.items():
        if code == transformations_obj.code_baseline:
            continue
        config = _transformation_to_config(transformation)
        (dir_path / f"transformation_{_slug(code)}.yaml").write_text(yaml.safe_dump(config, sort_keys=False))

    strategies_to_dataframe(strategies_map).to_csv(dir_path / STRATEGY_DEFINITIONS_FILENAME, index=False)

    fp_citations = dir_path / CITATIONS_FILENAME
    if not fp_citations.exists():
        fp_citations.write_text("")


def import_transformations_dir(
    dir_path: PathLike, transformers_catalog: trf.TransformerKernels
) -> Tuple[trf.Transformations, Dict[int, StrategyEntry]]:
    dir_path = pathlib.Path(dir_path)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"'{dir_path}' is not a directory.")
    if not (dir_path / CONFIG_GENERAL_FILENAME).exists():
        raise FileNotFoundError(
            f"'{dir_path}' doesn't look like a transformations directory "
            f"(missing {CONFIG_GENERAL_FILENAME})."
        )

    transformations_obj = trf.Transformations(dir_path, transformer_kernels=transformers_catalog)
    strategies_map = _parse_strategy_definitions(dir_path / STRATEGY_DEFINITIONS_FILENAME, transformations_obj)
    return transformations_obj, strategies_map


def export_session_zip(
    transformations_obj: trf.Transformations,
    strategies_map: Dict[int, StrategyEntry],
) -> bytes:
    tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="sisepuede_tool_export_"))
    export_transformations_dir(transformations_obj, strategies_map, tmp_dir)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in tmp_dir.iterdir():
            zf.write(fp, arcname=fp.name)
    return buffer.getvalue()


def import_session_zip(
    zip_path, transformers_catalog: trf.TransformerKernels
) -> Tuple[trf.Transformations, Dict[int, StrategyEntry]]:
    tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="sisepuede_tool_import_"))
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp_dir)

    return import_transformations_dir(tmp_dir, transformers_catalog)
