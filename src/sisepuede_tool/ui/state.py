"""Session-wide reactive state container.

One `AppState` is built per session (this app is local single-user, so in
practice once per `shiny run` process). Fields are grouped by which
milestone/page populates them; fields for pages not yet built are declared
here so the shape is stable, but stay unused/empty until that page lands.
"""

import dataclasses
from shiny import reactive


@dataclasses.dataclass
class AppState:
    # --- built at session init ---
    model_attributes: reactive.Value  # ModelAttributes
    transformer_metadata: reactive.Value  # dict -- resources/transformer_catalog.yaml (transformer_metadata_service)
    advanced_mode: reactive.Value  # bool -- the sidebar "Advanced options" switch
    transformers_catalog: reactive.Value  # Transformers | None -- built from the first baseline loaded
    models: reactive.Value  # SISEPUEDEModels | None -- built eagerly once the Run page (M4) is wired in

    # --- Baseline Data Manager (M1) ---
    baselines: reactive.Value  # Dict[str, BaselineDataset]
    default_baseline_id: reactive.Value  # str | None -- preselected in previews, dry runs and results

    # --- Transformer/Transformation Designer (M2) ---
    transformations_obj: reactive.Value  # sisepuede.transformers.transformations.Transformations | None
    # `transformations_obj` is mutated in place (dict_transformations, attribute_transformation) rather
    # than replaced -- reactive.Value.set() only invalidates on identity change (`self._value is value`),
    # not equality, so setting the *same* mutated object again is a silent no-op. This counter is bumped
    # on every mutation; anything that needs to react to transformations_obj changes must read this too.
    transformations_revision: reactive.Value  # int
    library_items: reactive.Value  # List[library_service.LibraryItem] -- NDC set, loaded with the first baseline

    # --- Strategy Builder (M3) ---
    strategies_map: reactive.Value  # Dict[int, StrategyEntry] -- starts with only {0: baseline}; ids > 0 are "pathways"
    active_pathway_id: reactive.Value  # int | None -- pathway open on the Pathways page
    # another page asks the Pathways page to open something:
    # {"type": "tx"|"new_tx"|"transformer", "value": code, "link_project": name|None, "nonce": int}
    pathways_request: reactive.Value

    # --- Run (M4) ---
    run_config: reactive.Value  # {"combinations": [(strategy_id, baseline_id), ...], "run_energy_production": bool}
    run_results: reactive.Value  # Dict[Tuple[int, str], RunResult]
    run_history: reactive.Value  # List[dict] -- newest first: strategy_id, baseline_id, ok, seconds, at, error

    # --- Costs and Benefits ---
    cb_wrapper: reactive.Value  # CBSSPWrapperForDFComparison | None -- built once at session start
    cb_results: reactive.Value  # Dict[str, Tuple[pd.DataFrame, pd.DataFrame]] keyed by baseline_id -- (df_cb, df_attr_variable)

    # --- Results pages (shared results bar) ---
    results_baseline_id: reactive.Value  # str | None -- baseline shown on the results pages (None = default baseline)
    results_pathways: reactive.Value  # frozenset[int] | None -- pathway chips switched on (None = all that ran)
    results_custom_vars: reactive.Value  # List[str] -- ModelVariables added as driver cards (advanced)

    # --- Output Explorer (M5) ---
    io_fields_cache: reactive.Value  # output variable catalog, built once from model_attributes

    # --- Validation (M6) ---
    validation_dataset: reactive.Value
    validation_crosswalk: reactive.Value

    # --- Projects ---
    selected_projects: reactive.Value  # Dict[str, bool] keyed by Project Name: "in scope"
    project_links: reactive.Value  # Dict[str, str | None] project name -> transformation code
    custom_projects: reactive.Value  # List[dict] -- projects added in the app (projects_service.make_custom_project)


def new_app_state() -> AppState:
    return AppState(
        model_attributes=reactive.Value(None),
        transformer_metadata=reactive.Value({"transformers": {}}),
        advanced_mode=reactive.Value(False),
        transformers_catalog=reactive.Value(None),
        models=reactive.Value(None),
        baselines=reactive.Value({}),
        default_baseline_id=reactive.Value(None),
        transformations_obj=reactive.Value(None),
        transformations_revision=reactive.Value(0),
        library_items=reactive.Value([]),
        strategies_map=reactive.Value({}),
        active_pathway_id=reactive.Value(None),
        pathways_request=reactive.Value(None),
        run_config=reactive.Value({"combinations": [], "run_energy_production": False}),
        run_results=reactive.Value({}),
        run_history=reactive.Value([]),
        cb_wrapper=reactive.Value(None),
        cb_results=reactive.Value({}),
        results_baseline_id=reactive.Value(None),
        results_pathways=reactive.Value(None),
        results_custom_vars=reactive.Value([]),
        io_fields_cache=reactive.Value(None),
        validation_dataset=reactive.Value(None),
        validation_crosswalk=reactive.Value(None),
        selected_projects=reactive.Value({}),
        project_links=reactive.Value({}),
        custom_projects=reactive.Value([]),
    )
