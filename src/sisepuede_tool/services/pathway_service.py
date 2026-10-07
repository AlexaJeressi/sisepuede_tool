"""Pathways: the UI name for sisepuede Strategies.

A pathway is a `StrategyEntry` (strategy id > 0) whose `transformation_codes`
may be empty: an empty pathway is built as a baseline-only Strategy so it can
still be run and compared.

`Strategy` captures its transformations' functions when it is constructed
(`Strategy._initialize_function`), so after any transformation is added,
updated or removed every pathway must be rebuilt (`rebuild_pathways`);
otherwise a pathway would keep running the old parameters.

Several transformations of the same transformer can be in one pathway.
sisepuede applies them one after another in transformation-code order
(`strategy_service.resolve_application_order`); how they should combine is
not defined yet, so the UI shows that order and warns (tracker, section 5).
"""

from collections import OrderedDict
from typing import Dict, Iterable, List, Optional, Tuple

import sisepuede.transformers as trf

from sisepuede_tool.models.strategy_entry import StrategyEntry
from sisepuede_tool.services import ramp_service, strategy_service, transformation_service

BAU_STRATEGY_ID = 0
PathwayMap = Dict[int, StrategyEntry]


##########################
#    BUILDING / EDITS    #
##########################


def build_pathway_strategy(
    strategy_id: int,
    transformation_codes: List[str],
    transformations_obj: trf.Transformations,
    name: str,
    description: str = "",
) -> trf.Strategy:
    codes = [c for c in transformation_codes if c != transformations_obj.code_baseline]
    if strategy_id == BAU_STRATEGY_ID:
        return strategy_service.build_baseline_strategy(transformations_obj)
    return strategy_service.build_strategy(
        strategy_id,
        codes or [transformations_obj.code_baseline],
        transformations_obj,
        name=name,
        description=description,
    )


def _description(entry: StrategyEntry) -> str:
    # Strategy only has .description when it was passed in dict_attributes
    return getattr(entry.strategy, "description", "") or ""


def _entry(strategy_id, codes, transformations_obj, name, description="") -> StrategyEntry:
    strategy = build_pathway_strategy(strategy_id, codes, transformations_obj, name, description)
    return StrategyEntry(strategy=strategy, transformation_codes=list(codes))


def pathway_ids(pathways: PathwayMap) -> List[int]:
    """User pathways (BAU excluded), in creation order."""
    return [sid for sid in pathways if sid != BAU_STRATEGY_ID]


def pathway_codes(entry: StrategyEntry, transformations_obj: trf.Transformations) -> List[str]:
    return [c for c in entry.transformation_codes if c != transformations_obj.code_baseline]


def create_pathway(
    pathways: PathwayMap,
    transformations_obj: trf.Transformations,
    name: str,
    copy_from: Optional[int] = None,
    description: str = "",
) -> Tuple[PathwayMap, int]:
    name = (name or "").strip()
    if not name:
        raise ValueError("A pathway needs a name.")
    if any(e.strategy.name == name for sid, e in pathways.items() if sid != BAU_STRATEGY_ID):
        raise ValueError(f"A pathway named '{name}' already exists.")
    codes: List[str] = []
    if copy_from is not None:
        codes = pathway_codes(pathways[copy_from], transformations_obj)
    sid = strategy_service.next_available_strategy_id(pathways.keys())
    out = dict(pathways)
    out[sid] = _entry(sid, codes, transformations_obj, name, description)
    return out, sid


def rename_pathway(pathways: PathwayMap, transformations_obj, sid: int, name: str) -> PathwayMap:
    name = (name or "").strip()
    if not name:
        raise ValueError("A pathway needs a name.")
    entry = pathways[sid]
    out = dict(pathways)
    out[sid] = _entry(sid, entry.transformation_codes, transformations_obj, name, _description(entry))
    return out


def add_library_pathway(
    pathways: PathwayMap,
    transformations_obj,
    library_items,
    name: str = "NDC",
    description: str = "",
    codes: Optional[Iterable[str]] = None,
) -> Tuple[PathwayMap, Optional[int]]:
    """Add a pathway holding the usable library transformations in `codes`
    (default: the NDC set). Returns (pathways, None) if none is usable."""
    usable = {i.code for i in library_items if i.ok and i.code in transformations_obj.dict_transformations}
    if codes is None:
        codes = [i.code for i in library_items if getattr(i, "source", "ndc") == "ndc"]
    codes = [c for c in codes if c in usable]
    if not codes:
        return pathways, None
    out, sid = create_pathway(pathways, transformations_obj, name, description=description)
    return set_pathway_codes(out, transformations_obj, sid, codes), sid


def delete_pathway(pathways: PathwayMap, sid: int) -> PathwayMap:
    if sid == BAU_STRATEGY_ID:
        raise ValueError("Business as usual cannot be removed.")
    out = dict(pathways)
    out.pop(sid, None)
    return out


def set_pathway_codes(pathways: PathwayMap, transformations_obj, sid: int, codes: Iterable[str]) -> PathwayMap:
    if sid == BAU_STRATEGY_ID:
        raise ValueError("Business as usual has no transformations.")
    entry = pathways[sid]
    codes = list(dict.fromkeys(c for c in codes if c != transformations_obj.code_baseline))
    out = dict(pathways)
    out[sid] = _entry(sid, codes, transformations_obj, entry.strategy.name, _description(entry))
    return out


def add_to_pathway(pathways: PathwayMap, transformations_obj, sid: int, code: str) -> PathwayMap:
    if code not in transformations_obj.dict_transformations:
        raise KeyError(f"Unknown transformation {code}")
    return set_pathway_codes(pathways, transformations_obj, sid, pathway_codes(pathways[sid], transformations_obj) + [code])


def remove_from_pathway(pathways: PathwayMap, transformations_obj, sid: int, code: str) -> PathwayMap:
    codes = [c for c in pathway_codes(pathways[sid], transformations_obj) if c != code]
    return set_pathway_codes(pathways, transformations_obj, sid, codes)


def rebuild_pathways(pathways: PathwayMap, transformations_obj: trf.Transformations) -> PathwayMap:
    """Rebuild every Strategy against the current transformations; codes that
    no longer exist are dropped from their pathway."""
    known = set(transformations_obj.dict_transformations)
    out = {}
    for sid, entry in pathways.items():
        codes = [c for c in entry.transformation_codes if c in known]
        out[sid] = _entry(sid, codes, transformations_obj, entry.strategy.name, _description(entry))
    return out


def save_transformation(
    pathways: PathwayMap,
    transformations_obj: trf.Transformations,
    transformation: trf.Transformation,
) -> PathwayMap:
    """Add or replace a transformation and rebuild every pathway."""
    transformation_service.add_transformation(transformations_obj, transformation)
    return rebuild_pathways(pathways, transformations_obj)


def delete_transformation(pathways: PathwayMap, transformations_obj, code: str) -> PathwayMap:
    used = pathways_using(code, pathways)
    if used:
        names = ", ".join(pathways[s].strategy.name for s in used)
        raise ValueError(f"{code} is used in {names}. Remove it from those pathways first.")
    transformation_service.remove_transformation(transformations_obj, code)
    return rebuild_pathways(pathways, transformations_obj)


##########################
#        QUERIES         #
##########################


def pathways_using(code: str, pathways: PathwayMap) -> List[int]:
    return [sid for sid, e in pathways.items() if sid != BAU_STRATEGY_ID and code in e.transformation_codes]


def transformations_by_transformer(transformations_obj: trf.Transformations) -> Dict[str, List[str]]:
    """transformer code -> its transformation codes (code order)."""
    out: Dict[str, List[str]] = {}
    for code in sorted(transformations_obj.dict_transformations):
        if code == transformations_obj.code_baseline:
            continue
        t = transformations_obj.dict_transformations[code]
        out.setdefault(t.transformer_code, []).append(code)
    return out


def grouped_pathway(entry: StrategyEntry, transformations_obj) -> "OrderedDict[str, List[str]]":
    """Pathway contents by transformer, each list in sisepuede application
    order; transformers ordered by their first application."""
    order = strategy_service.resolve_application_order(pathway_codes(entry, transformations_obj), transformations_obj)
    groups: "OrderedDict[str, List[str]]" = OrderedDict()
    for code in order:
        t = transformations_obj.dict_transformations[code]
        groups.setdefault(t.transformer_code, []).append(code)
    return groups


def stacked_transformers(entry: StrategyEntry, transformations_obj) -> List[str]:
    """Transformers with more than one transformation in the pathway."""
    return [tfr for tfr, codes in grouped_pathway(entry, transformations_obj).items() if len(codes) > 1]


##########################
#        SUMMARIES       #
##########################


def magnitude_of(
    transformation: trf.Transformation, magnitude_param: Optional[str], default: Optional[float] = None
) -> Optional[float]:
    if magnitude_param is None:
        return None
    value = (transformation.dict_parameters or {}).get(magnitude_param, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_magnitude(value: Optional[float]) -> str:
    if value is None:
        return "custom"
    if 0 <= value <= 1:
        pct = value * 100
        return f"{pct:.0f}%" if abs(pct - round(pct)) < 0.05 else f"{pct:.1f}%"
    return f"{value:g}"


def policy_ramp_of(transformation: trf.Transformation, years, default_ramp: Dict) -> ramp_service.PolicyRamp:
    ramp = (transformation.dict_parameters or {}).get("vec_implementation_ramp")
    if ramp is not None and not isinstance(ramp, dict):
        ramp = None  # a raw vector; describe with defaults
    return ramp_service.policy_from_ramp(ramp, years, default_ramp)


def summarize(
    transformation: trf.Transformation,
    magnitude_param: Optional[str],
    years,
    default_ramp: Dict,
    magnitude_default: Optional[float] = None,
) -> str:
    """'30% · 2026→2040 · S-curve'"""
    mag = format_magnitude(magnitude_of(transformation, magnitude_param, magnitude_default))
    return f"{mag} · {ramp_service.describe(policy_ramp_of(transformation, years, default_ramp))}"
