# Proposed basic / advanced parameters per transformer

Generated 2026-10-04 by `scripts/build_advanced_options_proposal.py` from the editor's specs.
Rules: main magnitude + implementation ramp = basic; guided tables from `resources/param_schemas.yaml` use their own `tier`; everything else = advanced; `return_*` hidden.
Change a parameter's tier with `tier:` in `param_schemas.yaml` or `resources/transformer_widget_metadata.yaml`.

⚠ = nothing but the ramp in basic mode.

## AFOLU

| Transformer | Status | Basic | Advanced |
|---|---|---|---|
| `TFR:AGRC:DEC_CH4_RICE`<br>Improve rice management | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:AGRC:DEC_EXPORTS`<br>Decrease Exports | no_effect_on_baseline | `magnitude` (Size of the change) + ramp | `magnitude_type` (How the size is applied) |
| `TFR:AGRC:DEC_LOSSES_SUPPLY_CHAIN`<br>Reduce supply chain losses | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:AGRC:INC_PRODUCTIVITY`<br>Improve crop productivity | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:AGRC:TARGET_RESIDUE_MANAGEMENT`<br>Target residue management | ok | `dict_categories_to_magnitude` (No-till share of cropland by the final year) — table + ramp | `include_conservation_agriculture` (Apply conservation agriculture)<br>`magnitude_burned` (Residues burned) — note only<br>`magnitude_removed` (Residues removed) — note only |
| `TFR:FRST:INCREASE_SEQUESTRATION`<br>Increase Sequestration | error | `magnitude` (Size of the change) + ramp | `cats_frst` (Forest types) |
| `TFR:FRST:TARGET_REMOVALS_DW`<br>Increase Deadwood Removals | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:LNDU:BOUND_CLASSES`<br>Bound Classes | no_effect_on_baseline | `dict_directional_categories_to_magnitude` (Area limits by land use class) — table + ramp | `delim_key` (Key separator) — note only |
| `TFR:LNDU:DEC_CLASS_LOSS`<br>Decrease loss of land use classes | ok | `magnitude` (Size of the change) + ramp | `cat_lndu` (Land use class to protect) |
| `TFR:LNDU:DEC_DEFORESTATION`<br>Stop deforestation | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:LNDU:DEC_SOC_LOSS_PASTURES`<br>Expand sustainable grazing practices | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:LNDU:INC_PRODUCTIVITY_PASTURES`<br>Increase Pasture Productivity | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:LNDU:INC_REFORESTATION`<br>Increase Reforestation | ok | `magnitude` (Size of the change) + ramp | `cats_inflow_restriction` (Land that new forest can't come from) |
| `TFR:LNDU:INC_SILVOPASTURE`<br>Expand silvopasture | error | `magnitude` (Size of the change) + ramp | — |
| `TFR:LNDU:PLUR`<br>Partial land use reallocation | ok | `magnitude` (Size of the change) + ramp | `force` (Force the reallocation) |
| `TFR:LSMM:INC_CAPTURE_BIOGAS`<br>Increase biogas capture at anaerobic decomposition facilities | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:LSMM:INC_MANAGEMENT_CATTLE_PIGS`<br>Improve manure management for cattle and pigs | ok | `dict_lsmm_pathways` (Manure management systems by the final year) — table, at most 100% + ramp | `vec_cats_lvst` (Animals) |
| `TFR:LSMM:INC_MANAGEMENT_OTHER`<br>Improve manure management for other animals | ok | `dict_lsmm_pathways` (Manure management systems by the final year) — table, at most 100% + ramp | `vec_cats_lvst` (Animals) |
| `TFR:LSMM:INC_MANAGEMENT_POULTRY`<br>Improve manure management for poultry | ok | `dict_lsmm_pathways` (Manure management systems by the final year) — table, at most 100% + ramp | `vec_cats_lvst` (Animals) |
| `TFR:LVST:DEC_ENTERIC_FERMENTATION`<br>Reduce enteric fermentation | ok | `dict_lvst_reductions` (Cut in enteric methane per animal) — table + ramp | — |
| `TFR:LVST:DEC_EXPORTS`<br>Decrease exports | no_effect_on_baseline | `magnitude` (Size of the change) + ramp | — |
| `TFR:LVST:INC_PRODUCTIVITY`<br>Increase livestock productivity | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:LVST:SHIFT_DIETARY_BOUNDS`<br>Shift Livestock Diets ⚠ | no_effect_on_baseline | — + ramp | `dict_lvst_shifts` (Livestock diet shifts) — note only |
| `TFR:SOIL:DEC_LIME_APPLIED`<br>Improve lime application | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:SOIL:DEC_N_APPLIED`<br>Improve fertilizer application | ok | `magnitude` (Size of the change) + ramp | — |

## Circular Economy

| Transformer | Status | Basic | Advanced |
|---|---|---|---|
| `TFR:TRWW:INC_CAPTURE_BIOGAS`<br>Increase biogas capture | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:TRWW:INC_COMPLIANCE_SEPTIC`<br>Increase septic compliance | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:WALI:INC_TREATMENT_INDUSTRIAL`<br>Improved industrial wastewater treatment | ok | `dict_magnitude` (Treatment pathways by the final year) — table, at most 100% + ramp | — |
| `TFR:WALI:INC_TREATMENT_RURAL`<br>Improved rural wastewater treatment | ok | `dict_magnitude` (Treatment pathways by the final year) — table, at most 100% + ramp | — |
| `TFR:WALI:INC_TREATMENT_URBAN`<br>Improved urban wastewater treatment | ok | `dict_magnitude` (Treatment pathways by the final year) — table, at most 100% + ramp | — |
| `TFR:WASO:DEC_CONSUMER_FOOD_WASTE`<br>Consumer food waste reduction | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:WASO:DEC_MCF_LANDFILLS`<br>Decrease average landfill methane correction factor | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:WASO:INC_ANAEROBIC_AND_COMPOST`<br>Increase composting and biogas | ok | `magnitude_biogas` (Share of waste to biogas) + ramp | `magnitude_compost` (Share of waste to compost) |
| `TFR:WASO:INC_CAPTURE_BIOGAS`<br>Increase biogas capture | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:WASO:INC_ENERGY_FROM_BIOGAS`<br>Biogas for energy production | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:WASO:INC_ENERGY_FROM_INCINERATION`<br>Incineration for energy production | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:WASO:INC_LANDFILLING`<br>Increase landfilling | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:WASO:INC_RECYCLING`<br>Increase recycling | ok | `magnitude` (Size of the change) + ramp | — |

## Energy

| Transformer | Status | Basic | Advanced |
|---|---|---|---|
| `TFR:CCSQ:INC_CAPTURE`<br>Increase direct air capture | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:ENFU:ADJ_EXPORTS`<br>Adjust Exports | ok | `magnitude` (Size of the change) + ramp | `magnitude_type` (How the size is applied) |
| `TFR:ENFU:ADJ_PRICES`<br>Adjust Prices | ok | `magnitude` (Size of the change) + ramp | `magnitude_type` (How the size is applied) |
| `TFR:ENTC:DEC_LOSSES`<br>Reduce transmission losses | ok | `magnitude` (Size of the change) + ramp | `magnitude_type` (How the size is applied)<br>`min_loss` (Lowest loss rate allowed) |
| `TFR:ENTC:INCREASE_EFFICIENCY_FUEL_PROD`<br>Increase efficiency of fuel production | no_effect_on_baseline | `dict_magnitudes` (Fuel production efficiency) — table + ramp | `kwargs` (Extra options) — note only |
| `TFR:ENTC:LEAST_COST_SOLUTION`<br>Least cost solution ⚠ | ok | — + ramp | `acceleration_factor` (Acceleration factor)<br>`drop_frac_elec_increase_for_msp` (Ignore electricity growth for minimum shares) |
| `TFR:ENTC:TARGET_CLEAN_HYDROGEN`<br>Clean hydrogen | ok | `magnitude` (Size of the change) + ramp | `categories_source` (Hydrogen production to replace)<br>`categories_target` (Clean hydrogen production) |
| `TFR:ENTC:TARGET_RENEWABLE_ELEC`<br>95% of electricity is generated by renewables in final time period | ok | `magnitude` (Size of the change) + ramp | `categories_entc_max_investment_ramp` (Technologies with capped investment growth)<br>`categories_entc_renewable` (Technologies counted as renewable)<br>`dict_entc_renewable_target_msp` (Minimum share of electricity by technology) — table<br>`scale_non_renewables_to_match_surplus_msp` (Scale non-renewables to fit the minimum shares) |
| `TFR:FGTV:DEC_LEAKS`<br>Minimize leaks | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:FGTV:INC_FLARE`<br>Maximize flaring | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:INEN:INC_EFFICIENCY_ENERGY`<br>Maximize industrial energy efficiency | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:INEN:INC_EFFICIENCY_PRODUCTION`<br>Maximize industrial production efficiency | ok | `magnitude` (Size of the change) + ramp | `categories` (Industries) |
| `TFR:INEN:SHIFT_FUEL_HEAT`<br>Fuel switch high- and low-temp thermal processes ⚠ | ok | — + ramp | `frac_high_given_high` (Share of heat demand that is high temperature) — table<br>`frac_switchable` (Share of heat demand that can switch fuel) |
| `TFR:SCOE:DEC_DEMAND_HEAT`<br>Reduce end-use demand for heat energy by improving building shell | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:SCOE:INC_EFFICIENCY_APPLIANCE`<br>Increase appliance efficiency | error | `magnitude` (Size of the change) + ramp | `categories` (Categories) |
| `TFR:SCOE:INC_EFFICIENCY_HEAT`<br>Increase heat efficiency | ok | `dict_cats_to_magnitude` (Heating efficiency gain by fuel) — table + ramp | — |
| `TFR:SCOE:SHIFT_FUEL_HEAT`<br>Switch to electricity for heat using heat pumps, electric stoves, etc. | ok | `magnitude` (Size of the change) + ramp | `cat_enfu_target` (Fuel to switch to)<br>`cats_enfu_source` (Fuels to switch from)<br>`cats_scoe_apply` (Building types) |
| `TFR:TRDE:DEC_DEMAND`<br>Reduce demand for transport | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:TRNS:INC_EFFICIENCY_ELECTRIC`<br>Increase electric transportation energy efficiency | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:TRNS:INC_EFFICIENCY_NON_ELECTRIC`<br>Increase non-electric transportation energy efficiency | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:TRNS:INC_OCCUPANCY_LIGHT_DUTY`<br>Increase occupancy for private vehicles | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:TRNS:SHIFT_FUEL_LIGHT_DUTY`<br>Electrify light duty road transport | ok | `magnitude` (Size of the change) + ramp | `categories` (Vehicle types)<br>`dict_fuel_allocation` (New fuel mix for the shifted share) — table, must total 100% |
| `TFR:TRNS:SHIFT_FUEL_MARITIME`<br>Fuel switch maritime | ok | `magnitude` (Size of the change) + ramp | `categories` (Vehicle types)<br>`dict_allocation_fuels_target` (New fuel mix for the shifted share) — table, must total 100%<br>`fuels_source` (Fuels to switch from) |
| `TFR:TRNS:SHIFT_FUEL_MEDIUM_DUTY`<br>Fuel switch medium duty road transport | ok | `magnitude` (Size of the change) + ramp | `categories` (Vehicle types)<br>`dict_allocation_fuels_target` (New fuel mix for the shifted share) — table, must total 100%<br>`fuels_source` (Fuels to switch from) |
| `TFR:TRNS:SHIFT_FUEL_RAIL`<br>Electrify rail | ok | `magnitude` (Size of the change) + ramp | `categories` (Vehicle types)<br>`dict_fuel_allocation` (New fuel mix for the shifted share) — table, must total 100% |
| `TFR:TRNS:SHIFT_MODE_FREIGHT`<br>Mode shift freight | ok | `magnitude` (Size of the change) + ramp | `categories_out` (Modes to shift from)<br>`dict_categories_target` (Where the freight goes) — note only |
| `TFR:TRNS:SHIFT_MODE_PASSENGER`<br>Mode shift passenger vehicles to others | ok | `magnitude` (Size of the change) + ramp | `categories_out` (Modes to shift from)<br>`dict_categories_target` (Where the passengers go) — note only |
| `TFR:TRNS:SHIFT_MODE_REGIONAL`<br>Mode shift regional passenger travel | ok | `dict_categories_out` (Share of each mode's travel to shift) — table, at most 100% + ramp | `dict_categories_target` (Where the travel goes) — note only |

## IPPU

| Transformer | Status | Basic | Advanced |
|---|---|---|---|
| `TFR:IPPU:DEC_CLINKER`<br>Reduce cement clinker | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:IPPU:DEC_DEMAND`<br>Demand management | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:IPPU:DEC_HFCS`<br>Reduce use of HFCs | ok | `magnitude` (Size of the change) + ramp | — |
| `TFR:IPPU:DEC_N2O`<br>Reduce Nitrous Oxide emissions | no_effect_on_baseline | `magnitude` (Size of the change) + ramp | — |
| `TFR:IPPU:DEC_OTHER_FCS`<br>Reduce other fluorinated compounds | no_effect_on_baseline | `magnitude` (Size of the change) + ramp | — |
| `TFR:IPPU:DEC_PFCS`<br>Reduce use of PFCs | ok | `magnitude` (Size of the change) + ramp | — |

## Socioeconomic

| Transformer | Status | Basic | Advanced |
|---|---|---|---|
| `TFR:GNRL:INC_DENSITY_URBAN`<br>Increase urban density | ok | `magnitude` (Size of the change) + ramp | — |

## ZZ - CROSS

| Transformer | Status | Basic | Advanced |
|---|---|---|---|
| `TFR:PFLO:INC_HEALTHIER_DIETS`<br>Change diets | ok | `magnitude_red_meat` (Cut in red meat consumption) + ramp | — |
| `TFR:PFLO:INC_IND_CCS`<br>Industrial carbon capture and sequestration | ok | `dict_magnitude_eff` (Share of CO₂ captured where installed) — table<br>`dict_magnitude_prev` (Share of plants with carbon capture) — table + ramp | — |

## Transformers with nothing but the ramp in basic mode

- `TFR:ENTC:LEAST_COST_SOLUTION`
- `TFR:INEN:SHIFT_FUEL_HEAT`
- `TFR:LVST:SHIFT_DIETARY_BOUNDS`
