"""Session-wide reactive state container.

One `AppState` is built per session (this app is local single-user, so in
practice once per `shiny run` process). Fields are grouped by which
milestone/page populates them; fields for pages not yet built are declared
here so the shape is stable, but stay unused/empty until that page lands.
"""

import dataclasses
from typing import Dict, Tuple

from shiny import reactive


@dataclasses.dataclass
class AppState:
    # --- built at session init ---
    model_attributes: reactive.Value  # ModelAttributes
    transformers_catalog: reactive.Value  # Transformers | None -- built from the first baseline loaded
    models: reactive.Value  # SISEPUEDEModels | None -- built eagerly once the Run page (M4) is wired in

    # --- Baseline Data Manager (M1) ---
    baselines: reactive.Value  # Dict[str, BaselineDataset]

    # --- Transformer/Transformation Designer (M2) ---
    transformations_obj: reactive.Value  # sisepuede.transformers.transformations.Transformations | None
    # `transformations_obj` is mutated in place (dict_transformations, attribute_transformation) rather
    # than replaced -- reactive.Value.set() only invalidates on identity change (`self._value is value`),
    # not equality, so setting the *same* mutated object again is a silent no-op. This counter is bumped
    # on every mutation; anything that needs to react to transformations_obj changes must read this too.
    transformations_revision: reactive.Value  # int

    # --- Strategy Builder (M3) ---
    strategies_map: reactive.Value  # Dict[int, StrategyEntry] -- starts with only {0: baseline}

    # --- Run (M4) ---
    run_config: reactive.Value  # {"combinations": [(strategy_id, baseline_id), ...], "run_energy_production": bool}
    run_results: reactive.Value  # Dict[Tuple[int, str], RunResult]

    # --- Output Explorer (M5) ---
    io_fields_cache: reactive.Value  # output variable catalog, built once from model_attributes

    # --- Validation (M6) ---
    validation_dataset: reactive.Value
    validation_crosswalk: reactive.Value

    # --- Projects ---
    selected_projects: reactive.Value  # Dict[str, bool] keyed by Project Name, dynamically loaded from the xlsx


def new_app_state() -> AppState:
    return AppState(
        model_attributes=reactive.Value(None),
        transformers_catalog=reactive.Value(None),
        models=reactive.Value(None),
        baselines=reactive.Value({}),
        transformations_obj=reactive.Value(None),
        transformations_revision=reactive.Value(0),
        strategies_map=reactive.Value({}),
        run_config=reactive.Value({"combinations": [], "run_energy_production": False}),
        run_results=reactive.Value({}),
        io_fields_cache=reactive.Value(None),
        validation_dataset=reactive.Value(None),
        validation_crosswalk=reactive.Value(None),
        selected_projects=reactive.Value({}),
    )
