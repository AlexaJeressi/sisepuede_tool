# MRV Console redesign tracker

Living document for the redesign of the sisepuede_tool Shiny app, following the
Claude Design prototype in `info/Emissions Modeling Console-4/`.
Plan of record: phases below. Update status, dates and commits as work lands.

## 0. Start here (next session)

**State on 2026-10-04:** Phases 1, 2 and 2.5 (tester feedback: guided dict
parameters, smooth range, sector chips, icon-rail sidebar, plain labels) are
done and tested. All work is **uncommitted** in the working tree
(`git status`). 173 tests pass:
`/opt/miniconda3/envs/ssp_biomass_env/bin/python -m pytest tests -q -p no:warnings`.

**On hold (user, 2026-10-04):** the gaps found after testing (results/baselines
not saved in the zip, autosave + snapshots, sidebar export/import, Download CSV
header buttons (done for the results pages on `ndc-v1`, 2026-10-05: one Excel download per page), NDC target line, Monitoring upload, two §7 bugs, a curation
phase). Ask before picking them up.

**Latest (2026-10-09, `ndc-v1`):** tester feedback round, see the §9 log entry for that date.

**Next: Phase 3** (section 3). On `ndc-v1`, 3.1, 3.2 and 3.4 are done (2026-10-05); the rest, in this order:
1. ~~3.1~~ Shared results sub-bar (baseline picker defaulting to
   `state.default_baseline_id`, pathway chips, run stamp from `state.run_history`).
2. ~~3.2~~ Emissions & drivers: small multiples per pathway, stacked by
   subsector via `ma.get_all_subsector_emission_total_fields(return_type="dict_abv")`
   from `state.run_results[(sid, bid)].df_output`; % vs BAU (strategy 0).
   Keep the current free explorer (`page_output_explorer.py`) under advanced.
   Use `output_service.build_field_catalog` for labels.
3. 3.3 Levers by pathway (new nav item under Results): per transformation, the
   intensity of its top input variable over time per pathway (from
   `RunResult.df_input`), with an inspector.
4. ~~3.4~~ Costs & benefits restyle (`cost_benefit_service`, `state.cb_results`) + NPV with a choice of discount rate.
5. 3.5 Monitoring: fix `page_monitoring.py:48` (`get_output_catalog` doesn't
   exist → use `get_variable_catalog`), status cards, OK/Watch/Review table.
6. 3.6 Project files: contents list, snapshots, and the local-folder save/load
   moved from `ui/page_transformations.py`; then delete
   `page_transformations.py` and `page_strategies.py` (not in the navigation).
7. 3.7 Macro / Article 6 placeholders in the new style.

**Map of the new code:**
- **Services:**
  - `param_schema_service` (+ `resources/param_schemas.yaml`): valid keys, units and sum rules for dict / category parameters → `WidgetKind.DICT_TABLE` / `SELECT` / `NOTE`
  - `transformer_metadata_service` (+ `scripts/build_transformer_metadata.py` → `resources/transformer_catalog.yaml`)
  - `ramp_service`
  - `pathway_service` (pathway = Strategy; `rebuild_pathways` after any transformation change)
  - `library_service` (NDC set → `resources/library/egypt_ndc/`, 18 transformations from `ssp_egypt@btr_invent` strategy 6003; branch `ndc-v1`)
  - `projects_service` (links: project → NDC transformation on the same transformer)
  - `labels`
  - `output_service.build_field_catalog`
- **UI:** `app_shell` (nav, Advanced switch → `body.advanced-on` / `.adv-only`,
  `mrvGoTo(id)`), `page_pathways`, `page_run`, `page_data_input`, `page_projects`,
  `components/param_widget` (`render_editor_params` / `read_editor_params`),
  `components/charts`.
- **Page click events** use one namespaced `ui_event` input carrying
  `{type, value}`. Cross-page handoff goes through `state.pathways_request`.

**Browser check:** Playwright venv + drivers in the session scratchpad
(gone tomorrow). Recreate: `python3 -m venv <dir> && <dir>/bin/pip install playwright`,
then `chromium.launch(channel="chrome")` (uses the installed Google Chrome).
Run the app: `shiny run --port 8000 src/sisepuede_tool/app.py`
(`SISEPUEDE_TOOL_LOG_LEVEL=DEBUG` for detail).

**Waiting on the user (section 4):**
- review of `transformer_catalog.yaml` and `docs/advanced_options_proposal.md`
- `ndc-v1` open items (section 4)
- counter-intuitive emission directions
- funder/online-year columns for projects

## 1. Goal and users

- **Users:** people who know some modeling, often former modelers, now in
  policy-making roles. Most of them should be able to build and run pathways
  without seeing raw sisepuede parameters.
- **Also:** every sisepuede tweak stays reachable behind a global
  **Advanced options** switch, for users who want it.
- **Target design:** light "Papyrus" theme; workflow Baseline → Pathways → Run;
  Results; MRV; optional Projects portfolio.

## 2. Decisions log

| Date | Decision |
|---|---|
| 2026-10-02 | Top-5 variables and "emissions if used alone" per transformer come from an **offline script** (`scripts/build_transformer_metadata.py`) that writes a **curated YAML** (`resources/transformer_catalog.yaml`). The app reads the YAML; computing live is only a fallback. |
| 2026-10-02 | Redesign **all pages, in phases** (1: shell + Pathways + Run; 2: Baseline + Projects/NDC news; 3: Results, MRV, Files). Macro and Article 6 stay placeholders. |
| 2026-10-02 | A **global "Advanced options" toggle** in the sidebar, off by default. The list of options it shows is still to be curated (section 4). |
| 2026-10-02 | Several transformations of the same transformer in one pathway: **show what sisepuede does now** (applied one after another, in attribute-table order) and warn. No Sum/Max rule until the combination method is defined. |
| 2026-10-02 | UI term "Pathway" = sisepuede `Strategy`. The Transformations and Strategies pages merge into one Pathways page. |

## 3. Phase checklist

Status: `todo` / `wip` / `done` / `blocked`.

### Phase 1 — foundation, Pathways, Run
| # | Task | Status | Commit |
|---|---|---|---|
| 1.1a | `scripts/build_transformer_metadata.py`: top input **and output** variables + direction per transformer | done 2026-10-02 | |
| 1.1b | Same script: sector/subsector emissions when used alone (no Julia; 2050 + cumulative), labeled by fp-model flags | done 2026-10-02 | |
| 1.1c | `resources/transformer_catalog.yaml` generated (65 ok, 7 no effect on Egypt, 3 upstream errors); `curated` blocks kept on re-run | done 2026-10-02 | |
| 1.1d | `services/transformer_metadata_service.py` (`get_card`: curated > computed > live diff) + `services/labels.py` | done 2026-10-02 | |
| 1.2a | `ParamSpec.tier` / `label`; default rule; `tier`/`label` overrides; `return_*` hidden; proposal in `docs/advanced_options_proposal.md` | done 2026-10-02 | |
| 1.2b | `services/ramp_service.py`: years + shape ↔ `vec_implementation_ramp` (checked against real transformer output) | done 2026-10-02 | |
| 1.2c | `param_widget.render_editor_params` / `read_editor_params`: % magnitude (exact value in advanced), policy ramp (years + shape; raw ramp in advanced), other params by tier. Dict params still JSON (advanced) | done 2026-10-02 | |
| 1.2d | ~~Fix `_SUBSECTOR_TO_CATEGORY_KEY`~~ not a bug: the real keys are `landuse`/`waste_liquid`/`waste_solid` | n/a | |
| 1.3a | `theme.css` with Papyrus tokens (light + dark) + component styles; pages scroll inside the main area | done 2026-10-02 | |
| 1.3b | New nav (Workflow / Results / MRV / Portfolio / System), step badges + meta lines, Advanced switch (`body.advanced-on` + `.adv-only`) | done 2026-10-02 | |
| 1.3c | `AppState`: `transformer_metadata`, `advanced_mode`, `library_items`, `active_pathway_id`, `run_history` (`project_links` and results context come with Phases 2/3) | done 2026-10-02 | |
| 1.4 | `ui/page_pathways.py` + `services/pathway_service.py`: transformer browser, transformer view, editor (new / edit / duplicate, edited state), application-order panel, pair warnings, tray, pathway create/copy/rename/delete | done 2026-10-02 | |
| 1.4b | `Transformations(...)` changing the shared catalog config: harmless for the default config the app writes; only an imported `config_general.yaml` would change it. Documented, not changed | n/a | |
| 1.5 | Run page: baseline × pathway matrix, automatic BAU, time estimate, history with inline errors + Retry, sectors / C&B reference under advanced, errors in the server log | done 2026-10-02 | |

### Phase 2 — Baseline, Projects / NDC news
| # | Task | Status | Commit |
|---|---|---|---|
| 2.1 | Baseline page: validate on file choice (checklist incl. missing model input fields), loaded table with default baseline / remove, preview with friendly names, sector chips, search, sparklines (`output_service.build_field_catalog`) | done 2026-10-02 | |
| 2.2 | `services/library_service.py`: NDC news YAMLs (copied to `resources/library/egypt_ndc_news/`) loaded into the session with the first baseline; 50 of 53 usable | done 2026-10-02 (pulled forward) | |
| 2.3 | Projects page: filters (sector / In NDC / Unlinked), scope, table with linked transformation, inspector (KPIs, Modeled as, NDC/LTS notes, sources), link / unlink / create transformation / open in Pathways, + Add project; Pathways editor shows and edits the same links; `project_links.csv` + `custom_projects.csv` in the zip | done 2026-10-02 | |

### Phase 2.5 — tester feedback (2026-10-04)
| # | Task | Status | Commit |
|---|---|---|---|
| 2.5a | Dict parameters as guided tables: `resources/param_schemas.yaml` (keys from the attribute tables, units, defaults, sum rules) + `services/param_schema_service.py`; `WidgetKind.DICT_TABLE` (shares / values / bounds / pairs) with live total and "Scale to 100%"; `eq1` / `leq1` enforced on save; blank table = parameter left out (sisepuede default); `note` for parameters sisepuede ignores. Fixed wrong category choices (LSMM animals, TRNS / SCOE fuels, single selects for `cat_lndu` / `cat_enfu_target`). Tables of transformers with no magnitude are basic. Test: the pre-filled table gives the same result as sisepuede's own default | done 2026-10-04 | |
| 2.5b | Magnitude: native range (no server traffic while dragging) writing to the exact-value input on release | done 2026-10-04 | |
| 2.5c | Sector filter chips (dotted pills) above the transformer search | done 2026-10-04 | |
| 2.5d | Sidebar as a 60px icon rail that opens on hover / focus, pin to keep open (localStorage) | done 2026-10-04 | |
| 2.5e | Plain labels everywhere (`labels.PARAM_LABELS` / `param_label`); sisepuede names only in an ⓘ tooltip shown in advanced mode | done 2026-10-04 | |
| 2.5f | `scripts/build_advanced_options_proposal.py` regenerates `docs/advanced_options_proposal.md` from the editor specs | done 2026-10-04 | |

### Phase 3 — Results, MRV, Files
| # | Task | Status | Commit |
|---|---|---|---|
| 3.1 | Shared results sub-bar (baseline, pathway chips, run stamp) + Excel download: `ui/components/results_bar.py`, `state.results_baseline_id / results_pathways` | done 2026-10-05 (`ndc-v1`) | |
| 3.2 | Emissions & drivers (`ui/page_emissions.py`, replaces `page_output_explorer.py`): KPI tiles; small multiples by subsector or change vs BAU (2030/2050); subsector focus → detail + gas (`services/emissions_service.py`, rules ported from Egypt's `tableau_postprocessing.py`); curated driver cards per area (`resources/results_groups.yaml`, `services/results_groups_service.py`); advanced "Add a variable" cards (saved in the zip as `results_custom_vars.csv`); no tables, Excel download (`services/download_service.py`) | done 2026-10-05 (`ndc-v1`) | |
| 3.3 | Levers by pathway | todo | |
| 3.4 | Costs & benefits: stacked ± bars by category (17 `cb_type` → 10 categories) or sector, billion USD or % of GDP, net line; NPV at 3/5/7% (any rate in advanced), B/C ratio, net-positive year, NPV by category (`services/cb_summary_service.py`); no tables, Excel download. "By transformation" view still to do (needs `transformation_costs.transformation_code` mapping) | done 2026-10-05 (`ndc-v1`) | |
| 3.5 | Monitoring: fix `get_output_catalog`, status cards, OK/Watch/Review table | todo | |
| 3.6 | Project files: export/import contents list, snapshots; **move the local-folder save/load (macOS picker) from the retired `page_transformations.py`, then delete `page_transformations.py` and `page_strategies.py`** | todo | |
| 3.7 | Macro / Article 6 placeholders in the new style | todo | |

## 4. Curation tasks (need the user's review)

- [ ] **Transformer catalog YAML** (`resources/transformer_catalog.yaml`): review the
      friendly names, magnitude labels, top-5 variables, emission direction and
      `pair_with` per transformer, then set `source: curated` on each reviewed entry.
- [ ] **Advanced-options list.** Proposed default, to be confirmed:
  - **Basic:** main `magnitude*` (as % or a value with a friendly label);
    ramp as start year / full-effect year / shape (Linear, S-curve, Front-loaded, Back-loaded).
  - **Advanced:** raw ramp (`tp_0_ramp`, `n_tp_ramp`, `alpha_logistic`,
    `window_logistic`), `magnitude_type`, category lists, `dict_*`, booleans,
    secondary magnitudes, YAML preview, sectors to run, free variable explorer.
  - **Always hidden:** `return_*` helper flags.
  - Per-parameter overrides live in `resources/transformer_widget_metadata.yaml`
    (`tier`, `label`).
  - Full per-transformer proposal: `docs/advanced_options_proposal.md`
    (regenerate with `python scripts/build_advanced_options_proposal.py`).
    Since 2.5a the dict-only transformers show their table in basic mode;
    only 3 are left with nothing but the ramp: `ENTC:LEAST_COST_SOLUTION`,
    `INEN:SHIFT_FUEL_HEAT` (its lever is probably `frac_switchable`) and
    `LVST:SHIFT_DIETARY_BOUNDS` (not implemented upstream). Decide these.
  - Check the labels, help texts and tiers in `resources/param_schemas.yaml`.
  - Main-magnitude picks to check: `AGRC:TARGET_RESIDUE_MANAGEMENT` picked
    `magnitude_burned` (default 0); `magnitude_removed` is probably the right
    one. `INEN:SHIFT_FUEL_HEAT`'s lever is `frac_switchable`.
    `SCOE:INC_EFFICIENCY_HEAT`'s `dict_cats_to_magnitude` is a number.
- [ ] **Emission directions that look counter-intuitive** with default
      parameters on Egypt (2050, without NemoMod). Check them, and set
      `curated.emissions_direction` + `notes` where needed:
      `LNDU:INC_REFORESTATION` (+0.07%), `GNRL:INC_DENSITY_URBAN` (+0.14%),
      `PFLO:INC_HEALTHIER_DIETS` (+0.14%), `LSMM:INC_MANAGEMENT_OTHER` (+0.6%),
      `WALI:INC_TREATMENT_INDUSTRIAL` (+1.1%), `LNDU:PLUR` (+2.0%),
      `LNDU:INC_PRODUCTIVITY_PASTURES` (+1.0%).
- [ ] **No effect on the Egypt baseline** with defaults: `AGRC:DEC_EXPORTS`,
      `LVST:DEC_EXPORTS`, `ENTC:INCREASE_EFFICIENCY_FUEL_PROD`, `IPPU:DEC_N2O`,
      `IPPU:DEC_OTHER_FCS`, `LNDU:BOUND_CLASSES`, `LVST:SHIFT_DIETARY_BOUNDS`.
      Hide them in basic mode, or keep them with a note?
- [x] ~~**NDC news files that can't be used**~~ (obsolete on `ndc-v1`: the news library was removed) with the installed sisepuede
      (the loader reports them, the UI hides them):
      `NEWS_04`, `NEWS_05` → `TFR:AGRC:INC_CONSERVATION_AGRICULTURE` (folded
      upstream into `TARGET_RESIDUE_MANAGEMENT`, different parameters);
      `NEWS_24` → `TFR:FGTV:INC_GAS_RECOVERY` (no longer exists).
      `NEWS_34`, `NEWS_35` load but fail when run (`SCOE:INC_EFFICIENCY_APPLIANCE`
      upstream bug). Re-map or re-author them?
- [x] ~~**Project ↔ transformation links**~~ (superseded on `ndc-v1`, see below): NEWS_NN ↔ workbook row confirmed (all 53 match by project name, 2026-10-02). Default links come from that; NEWS_04/05/24 projects start unlinked because their transformers are missing.
- **`ndc-v1` (2026-10-05)**: the 53 per-news transformations are replaced by
      the 18 transformations of Egypt's NDC strategy (`6003 PFLO:NDC`,
      `ssp_egypt@btr_invent`), parameters copied verbatim, codes kept
      (`TX:…_STRATEGY_NDC`). Each project links to the NDC transformation on its
      transformer (43 linked, 10 unlinked). An "NDC" pathway is preloaded with the
      first baseline.
  - [ ] `AGRC:INC_CONSERVATION_AGRICULTURE` dropped (transformer folded upstream
        into `TARGET_RESIDUE_MANAGEMENT`); its 2 projects are unlinked. Re-author?
  - [ ] `ENTC:TARGET_RENEWABLE_ELEC`: the YAML (0.85; wind 0.5 / solar 0.35;
        tp_0_ramp 2) is used. The Egypt `entc_ndc_calibration.ipynb` has 0.45;
        0.198 / 0.25; ramp 8/9 (calibrated to −37% generation emissions 2030). Which is right?
  - [ ] `AGRC:DEC_CH4_RICE` and `SCOE:SHIFT_FUEL_HEAT` have no projects.
- [ ] Projects: the workbook has no funder column (the design shows one) and no structured online year; add them if wanted.

## 5. Open model questions

- **Ramp shape presets** (`ramp_service.SHAPES`, chosen 2026-10-02): Linear
  α=0; S-curve α=1, window (−5,5); Front-loaded α=1, (−3,6); Back-loaded
  α=1, (−6,3). "Starts in" = first year with any change (`tp_0_ramp` + 1);
  "Full effect by" = `tp_0_ramp + n_tp_ramp`. Other shapes show as "Custom"
  (advanced only).
- **Emissions classification heuristic** (`classify_emissions`): if
  `requires_fp_model_for_primary_effect` = 1, codes with SHIFT_FUEL /
  CLEAN_HYDROGEN become `depends_on_grid`, and others with no change without
  NemoMod become `needs_electricity_model`. "No change" threshold: 0.05% of
  total 2050 emissions.

- How several transformations of the same transformer should combine in one
  pathway (the design's Sum/Max is a placeholder). Currently they are applied
  in sequence, so the result depends on `magnitude_type`.
- "Emissions if used alone" for ENTC/TRNS/INEN transformers that need the
  electricity model (`requires_fp_model_for_primary_effect = 1`): without
  NemoMod the direction may be misleading. For now they are labeled
  "depends on the grid".
- Ramp `d` is validated but has no effect (`transformer_kernels.py:1891`).
  Front-/back-loaded shapes need an asymmetric `window_logistic`; check this.
- Application order: sisepuede applies transformations in attribute-table order,
  so the design's drag-to-reorder cannot be supported.

- The baseline "missing inputs" check uses `ModelAttributes.all_variable_fields_input`.
  Some NemoMod columns (e.g. `nemomod_entc_grid_power_constraint_mmm_usd`) are not
  model variable fields there, so their absence can't be flagged.

## 6. Upstream bugs to report (jcsyme/sisepuede, biomass_fix @ 699ac6e) — do not edit the clone

| Where | Problem |
|---|---|
| `transformers/lib/_baselib_afolu.py:815,1680,1724,1730` | uses `model_afolu.modvar_frst_biomass_growth_rate_co2`, which was renamed; breaks `FRST:INCREASE_SEQUESTRATION`, `LNDU:INC_SILVOPASTURE` and makes `get_tkernel_variable_fields()` crash |
| `transformer_kernels.py:7101` / `_baselib_energy.py:2605` | `SCOE:INC_EFFICIENCY_APPLIANCE` passes `categories=` into `transformation_general` → TypeError |
| `transformer_kernels.py:3306` | `AGRC:DEC_EXPORTS` uses `self.vec_implementation_ramp`, so a user ramp is ignored |
| `transformer_kernels.py:1891` | ramp `d` is validated but never used |
| `transformers/lib/_operations.py:587` and `:144,161,172,210` | still call `get_transformer_kernel` / `.transformers` (renamed) |
| `ref/ingestion/demo` (removed in 0928ee1) | `Strategies(...)` and `SISEPUEDE("demo")` fail in `BaseInputDatabase` |
| `manager/sisepuede_file_structure.py:319-322` | error message uses `self.dir_ingestion` before it is set |
| `transformer_kernels.py:2044-2045` (`check_trns_tech_allocation_dict`) | the result of the sum check is overwritten, so `dict_categories_target` of TRNS:SHIFT_MODE_FREIGHT / PASSENGER / REGIONAL is always ignored (default split used) |
| `transformer_kernels.py:5098` | `LVST:SHIFT_DIETARY_BOUNDS` is not implemented (returns the input) |
| `transformer_kernels.py:3731-3767` | `AGRC:TARGET_RESIDUE_MANAGEMENT`: `magnitude_burned` / `magnitude_removed` are inside a disabled string block; with `include_conservation_agriculture=False` it raises UnboundLocalError |
| `transformer_kernels.py:6777` | `INEN:SHIFT_FUEL_HEAT`: the low-temperature category list always comes from the config default, not from `frac_high_given_high` |
| `transformer_kernels.py:2574`, `_baselib_energy.py:1117-1130` | `ENTC:TARGET_RENEWABLE_ELEC`: passing `categories_entc_renewable` as a list takes the renewables from the MSP dict keys; with an empty dict the transformer silently does nothing |
| `_baselib_afolu.py:1942`, `_baselib_circular_economy.py:283` | LSMM / WALI shares above 1 make the transformation a silent no-op (no error) |
| `transformer_kernels.py:4032`, `:7099` | a dict `magnitude` is silently replaced by the default in LNDU:INC_PRODUCTIVITY_PASTURES and SCOE:INC_EFFICIENCY_APPLIANCE |
| attribute table | `TRNS:SHIFT_MODE_FREIGHT`'s `units_description` is copied from WASO:DEC_MCF_LANDFILLS (app shows a curated `magnitude_help` instead) |
| attribute table | `AGRC:DEC_DEMAND_FOR_UNHEALTHY_CROPS`, `LNDU:INC_LAND_REHABILITIATION` listed but not implemented; `variables_affected` and `citations` are empty |

## 7. App bugs found and fixed

| Bug | Status |
|---|---|
| `page_monitoring.py:48` calls missing `output_service.get_output_catalog` | todo |
| ~~`widget_metadata._SUBSECTOR_TO_CATEGORY_KEY` wrong keys~~: checked 2026-10-02, the keys match sisepuede | not a bug |
| `Transformations(..., transformer_kernels=catalog)` changes the shared catalog config | todo |
| `CB_CONFIG_XLSX_PATH` points at a test fixture | todo |
| An empty multi-select was saved as `()` / `[]` instead of `None` (sisepuede's default categories): `read_params` now returns `None` for an empty selection and lists for tuples | fixed 2026-10-02 |
| Pathways didn't pick up an edited transformation: `Strategy` captures functions at build time, so every pathway is now rebuilt after a transformation changes (`pathway_service.rebuild_pathways`) | fixed 2026-10-02 |
| Empty strategies couldn't be exported/imported (`build_strategy` rejects no codes): written as `TX:BASE`, read back as an empty pathway | fixed 2026-10-02 |
| Category lists took their choices from the transformer's subsector table: LSMM `vec_cats_lvst` offered manure systems, TRNS `fuels_source` modes, SCOE `cats_enfu_source` building types | fixed 2026-10-04 (`param_schemas.yaml`) |
| Magnitude slider lagged while dragging (every tick went to the server and re-rendered the edit status) | fixed 2026-10-04 (native range) |
| Run / C&B errors only in the UI | fixed 2026-10-02: logged by `sisepuede_tool.ui.page_run`; `SISEPUEDE_TOOL_LOG_LEVEL=DEBUG` for more |
| `tests/test_widget_metadata.py::test_bool_param` used `TFR:AGRC:INC_CONSERVATION_AGRICULTURE`, which no longer exists upstream (folded into `TARGET_RESIDUE_MANAGEMENT`) | fixed 2026-10-02 |

## 8. Design deviations

- No drag-to-reorder in pathways (sisepuede imposes the order); the resolved
  order is shown instead.
- No Sum/Max combination control (see section 5).
- Library (NDC) transformations are read-only in the editor: "Duplicate &
  adjust" makes an editable copy, so the published version stays intact.
- Business as usual is not a pathway tab; it is the first column of the Run
  matrix and is added automatically for every baseline used.
- Sector chips and the C&B reference strategy on the Run page are advanced
  options (the design shows sector chips always); revisit in curation.
- The baseline picker in the Pathways strip is not implemented (pathways do not
  depend on a baseline until run); the strip shows which baseline the catalog
  was built from.

## 9. Log

- **2026-10-02**: tracker created. Phase 1.1 (metadata script, YAML,
  service) and 1.2a/b (tiers, ramp service) done; 109 tests pass (run tests
  that need Julia not included). Regenerate the YAML with
  `python scripts/build_transformer_metadata.py` (~2 min, no Julia).
- **2026-10-02 (b)**: Phase 1 UI done: theme/shell, Pathways page, Run
  page, NDC library loaded into the session. 128 tests pass (including the
  Julia run tests). Driven end to end in headless Chrome (Playwright in a
  scratch venv): load baseline → create pathway → transformation from default
  → add NDC news item → run without NemoMod (BAU + pathway OK).
- **2026-10-02 (c)**: Phase 2 done: Baseline page, Projects page with
  project ↔ transformation links shared with the Pathways editor, links and
  custom projects saved in the session zip. 141 tests pass. Driven in headless
  Chrome: old baseline (missing input) warning, two baselines + default,
  preview search, link/unlink, create a transformation from a project, open a
  linked one in Pathways, export zip contains `project_links.csv`.
- **2026-10-04**: Phase 2.5 (tester feedback) done: guided dict tables from
  `param_schemas.yaml`, native magnitude range, sector chips, icon-rail
  sidebar, plain labels with ⓘ tooltips. 173 tests pass. Driven in headless
  Chrome: rail 60→216px on hover and pin kept after reload; Circular Economy
  chip filters the list; WALI urban at 130% blocked on save, cleared back to
  default; TRNS light-duty fuel mix 60/20 → "Scale to 100%" → 75/25 saved;
  ENTC fuel-production pair saved; no websocket traffic while dragging the
  magnitude, value saved on release; no raw sisepuede names in advanced mode.
- **2026-10-05**: the app is always light, like the design (which has no dark
  mode). The automatic `prefers-color-scheme: dark` switch was removed; the
  dark palette stays behind `<html data-theme="dark">`. Also removed the 10px
  page padding left of the sidebar.
- **2026-10-05 (b)**: larger text: every font size in `theme.css` and the
  inline ones in the pages scaled ×1.1 (base 13.5 → 15px). Pathways columns
  widened: transformers 300 → 380px, "In this pathway" 290 → 330px; the
  editor's form column gets 1.35× the ramp column.
- **2026-10-05 (c)**: Egypt flag back (region box + top of the collapsed
  rail). Pathways filter chips are now by **subsector** (one row per sector,
  labels from sisepuede's subsector table, shortened for CCSQ / LSMM / SCOE /
  TRDE / PFLO / GNRL; code on hover), in a collapsible "Subsectors" block whose
  summary lists the selection. Open sidebar 216 → 236px for the larger text.
- **2026-10-05 (d)**: transformer list and filter grouped by 8 **policy
  areas** instead of 19 subsectors (`page_pathways._AREAS`): Electricity &
  fuels (ENTC, ENFU, FGTV, CCSQ), Transport (TRNS, TRDE), Buildings (SCOE),
  Industry (INEN, IPPU + PFLO:INC_IND_CCS), Agriculture & food (AGRC, LVST,
  LSMM, SOIL + PFLO:INC_HEALTHIER_DIETS), Land & forests (LNDU, FRST), Waste
  (WASO, WALI, TRWW), Cross-cutting (GNRL). Chips coloured by sector; the
  subsector codes show on hover.
- **2026-10-05 (`ndc-v1`)**: results redesign (3.1, 3.2, 3.4). The emission
  detail matches `emission_co2e_subsector_total_*` to within 1e-5 Mt once three
  differences in the installed sisepuede are handled: biogenic CO₂ from INEN and
  SCOE (`_bmass_`) is left out of the totals; the land-use "converted away"
  roll-ups are now `conversion_{agb,bgb}_away_`; and AGRC/FRST have new
  categories (`residue_*`, `woody_biomass`, `decomposition`,
  `fuelwood_removals`). Four driver cards (generation, capacity, grid losses,
  fuel production) need the electricity model; the page says so instead of
  showing an empty card. 186 tests pass (13 new in
  `tests/test_results_services.py`). Driven in headless Chrome: Egypt
  baseline → BAU + NDC with NemoMod → both pages, subsector focus
  (Transportation), Change vs BAU, 3%/% of GDP/By sector, both downloads,
  advanced add/remove card, custom 10% rate.
- **2026-10-05 (`ndc-v1`, later)**: C&B totals are **not discounted by default**
  (user: the team usually doesn't discount; the C&B module doesn't either). A
  discount rate (3/5/7% or any) is an advanced option; the title then switches to
  "Net present value". Excel has totals at 0/3/5/7%. Added "Largest items"
  (item-level totals with a category filter) and readable item names where the
  C&B config's display name is missing or a shared placeholder (all 47 enfu
  fuel_cost rows are "Fuel Cost bio fuel_biogas": fix in the config). ⓘ are
  click-to-open bubbles (`ui/components/info_tip.py`); modals themed; chart
  legends on the right. 189 tests pass.
- **2026-10-09 (`ndc-v1`, pushed 3aec49d / cf5e312 / e5ed0b7)**: tester feedback.
  - Names: transformers whose names implied a fixed size got curated names in
    `transformer_catalog.yaml` ("95% of electricity…" → "Renewable electricity
    target"; Stop/Maximize/Minimize → Reduce/Increase); NDC/LEP library names
    to match. Descriptions with default numbers ("by 45%") are still as-is.
  - Electricity dispatch: `transformer_metadata_service.electricity_need()` from
    the attribute table's `requires_fp_model_for_{primary,full}_effect`
    (needed = primary, optional = full only; 29 / 31 / 15 of 75). Run page: one-line
    warning/ok under the switch, with a short ⓘ (no list of transformers, user
    request). Pathways: a note per transformer and a count in the tray (no ⚡ icon).
  - Editor: the trajectory chart sits under magnitude / Exact value, left of
    the timing controls.
  - Emissions & drivers: **one subsector selection** shown in the chart filter
    and the drivers header ("What drives [subsector] emissions"), two-way.
    Picking a subsector only **filters** the chart to that subsector (user: same
    sisepuede subsectors in both, don't swap them for other categories); the
    IPCC-style breakdown by source is an advanced switch. Gas filter always on
    (`emissions_service.by_subsector_for_gas`). Driver cards tagged with
    `subsectors` in `results_groups.yaml`; other cards of the area are dimmed under
    "Related subsectors · …". With "All subsectors": only Population/GDP, a hint
    and "Biggest changes vs BAU in 2050" shortcuts. The drivers header is sticky;
    Population & GDP can be hidden. 209 tests pass.
  - Seen, not fixed: Forest shows a ~3 Mt spike in 2015 (first period, from the data).
  - `README.md` has older uncommitted edits (not from this session): ask the user.
