"""Export/import Transformations + Strategies to/from sisepuede-native
project files (config_general.yaml, transformation_*.yaml,
strategy_definitions.csv), for reuse in the CLI or notebooks.

Export/import are explicit, user-triggered actions -- state is otherwise
session-only in memory (see the plan's Persistence section). Export bundles
everything into a single in-memory .zip for browser download rather than
writing to an arbitrary server path with no confirmation; import extracts
an uploaded .zip into a fresh temp directory and wraps the existing
`Transformations(dir, transformers=...)` directory constructor (read-only
at construction) -- `strategy_definitions.csv` is hand-parsed into bare
`Strategy` objects rather than instantiating the `Strategies` collection,
which has real file-system write side effects on construction.
"""

import io
import pathlib
import re
import tempfile
import zipfile
from typing import Dict, Tuple

import pandas as pd
import yaml
import sisepuede.transformers as trf

from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import strategy_service

STRATEGY_DEFINITIONS_FILENAME = "strategy_definitions.csv"


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


def export_session_zip(
    transformations_obj: trf.Transformations,
    strategies_map: Dict[int, StrategyEntry],
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        fp_general = transformations_obj.dict_paths.get(transformations_obj.key_path_config_general)
        zf.write(fp_general, arcname="config_general.yaml")

        for code, transformation in transformations_obj.dict_transformations.items():
            if code == transformations_obj.code_baseline:
                continue
            config = _transformation_to_config(transformation)
            zf.writestr(f"transformation_{_slug(code)}.yaml", yaml.safe_dump(config, sort_keys=False))

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
        strategy_df = pd.DataFrame(
            rows,
            columns=["strategy_id", "strategy_code", "strategy", "description", "transformation_specification"],
        )
        zf.writestr(STRATEGY_DEFINITIONS_FILENAME, strategy_df.to_csv(index=False))

    return buffer.getvalue()


def import_session_zip(
    zip_path, transformers_catalog: trf.Transformers
) -> Tuple[trf.Transformations, Dict[int, StrategyEntry]]:
    tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="sisepuede_tool_import_"))
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp_dir)

    transformations_obj = trf.Transformations(tmp_dir, transformers=transformers_catalog)

    strategies_map: Dict[int, StrategyEntry] = {}
    fp_strategies = tmp_dir / STRATEGY_DEFINITIONS_FILENAME
    if fp_strategies.exists():
        df = pd.read_csv(fp_strategies)
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

    return transformations_obj, strategies_map
