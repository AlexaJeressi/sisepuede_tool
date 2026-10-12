# sisepuede_tool

A [Shiny for Python](https://shiny.posit.co/py/) web app for building
decarbonization pathways with the
[SISEPUEDE](https://github.com/jcsyme/sisepuede) model. You load a baseline
dataset, put transformations together into pathways, run them, and compare
emissions and costs & benefits against business as usual. The *Article 6* tab
estimates the carbon credits a pathway could sell for going beyond the NDC.

This branch (`ndc-v1`) is the Egypt NDC version. It ships with a library of
NDC and LEP transformations and an example input file.

## Requirements

- **conda.** We recommend [Miniforge](https://github.com/conda-forge/miniforge).
  Any conda or mamba install also works.
- **git**, because pip installs `sisepuede` and `costs_benefits_ssp` straight
  from GitHub.
- **Internet access** for the first install and the first model run.
- About **5 GB** of free disk space for the Python env plus Julia and its
  solvers.

You don't need to install Julia yourself. The first time the energy model runs,
SISEPUEDE downloads the Julia version it needs (see
[First run](#first-run-takes-a-few-minutes)).

Development and testing were done on macOS. Linux should work too. Windows
hasn't been tested.

## Installation

```bash
git clone https://github.com/AlexaJeressi/sisepuede_tool.git
cd sisepuede_tool
git checkout ndc-v1          # the NDC version; skip if you want `main`

conda env create -f environment.yml
conda activate ssp_biomass_env
```

`environment.yml` sets up a conda env named `ssp_biomass_env` with:

- Python 3.13 (SISEPUEDE requires exactly 3.13)
- the geospatial and scientific packages SISEPUEDE needs, from conda-forge
- `sisepuede` from the `biomass_fix` branch on GitHub
- `costs_benefits_ssp` from GitHub (the version on PyPI is a different one)
- this repo itself, installed in editable mode with its dev extras (shiny,
  shinywidgets, plotly, pytest, ...)

Run `conda env create` from the repo root, because the env file installs `.`
in editable mode.

## Running the app

```bash
conda activate ssp_biomass_env
shiny run --launch-browser src/sisepuede_tool/app.py
```

The app opens at <http://127.0.0.1:8000>. Two variations:

```bash
# auto-reload when you edit the code
shiny run --reload --launch-browser src/sisepuede_tool/app.py

# keep a log of the server output (handy for debugging failed runs)
mkdir -p logs && shiny run --launch-browser src/sisepuede_tool/app.py 2>&1 | tee logs/app_$(date +%Y%m%d_%H%M%S).log
```

You can also start it with the `sisepuede-tool` command, which the editable
install adds.

### First run takes a few minutes

The first time you run a pathway, SISEPUEDE installs Julia 1.13 and the
NemoMod energy model with its solvers (via `juliapkg`). This takes **about 4
minutes**, and the log shows nothing past `Importing Julia...` while it
happens. That's expected: it only happens once and nothing has hung.

## Quick start

1. **Baseline data**: the example input file
   `tests/fixtures/example_input.csv` is loaded automatically as
   *Example input* when the app starts. It's an example input, not Egypt's
   actual baseline. To use your own, upload a baseline CSV and click
   *Add baseline* (and remove *Example input* with × if you don't need it).
2. **Pathways**: open a transformer, reuse an NDC transformation or create
   your own, and add it to a pathway.
3. **Run**: pick the baselines and pathways you want and run them.
4. **Results**: look at *Emissions & drivers* and *Costs & benefits*. Both
   are compared against business as usual. *Article 6* shows the credits of
   the pathways that go beyond the NDC (see [Article 6](#article-6)).

The first baseline you add sets the region for the whole session. Every
baseline after that has to be for the same region.

## Article 6

The *Article 6* tab estimates the credits a country could transfer under
Article 6 of the Paris Agreement: the emission reductions a pathway achieves
**beyond its NDC target**, valued at a carbon price. The calculation is ported
from [`sisepuede_a6`](https://github.com/jcsyme/sisepuede_a6) (`ssp_asix.py`).

For each NDC target year (2030 and 2035) and each emission group (Agriculture,
Transportation, IPPU, ...):

```
credits (MtCO2e) = NDC target − pathway emissions, if positive; otherwise 0
value (million USD) = credits × carbon price of that year (USD/tCO2e)
```

- Each group counts on its own: a group above its target earns nothing and
  doesn't reduce the credits of another group.
- Only pathways that go **beyond the NDC** are shown. The NDC targets are the
  NDC pathway's own emissions, so business as usual and pathways made only of
  NDC transformations earn no credits and are listed as "Not shown".
- The app preloads two pathways when you add the first baseline: **NDC**
  (strategy 6003) and **LEP** (strategy 6005, "Example LEP pathway used to
  demonstrate A6 opportunities": 13 NDC transformations plus 9 higher-ambition
  LEP ones). Both come from the
  [`ssp_egypt`](https://github.com/sisepuede-framework/ssp_egypt) repo, branch
  `btr_invent`. Run LEP to see credits.
- **Carbon price.** The page shows the price used for each target year. Turn on
  *Advanced options* (sidebar) to change it per year. The tiles, chart and
  download update right away without a new run; *Reset to reference prices*
  goes back.
- **Electricity model.** Electricity (Energy Technology) and fugitive emissions
  are only computed when *Run electricity dispatch (NemoMod)* is ticked on the
  *Run* page. Without it those two groups are left out, and the page says so.
- The *Download data (.xlsx)* button exports every group, year and pathway
  (emissions, target, surplus, credits, price, value), plus the targets, prices
  and groupings used.

The NDC targets, carbon prices and emission groupings are the example files from
`sisepuede_a6`, in `src/sisepuede_tool/resources/article6/`. Replace those CSVs
(same columns) to use other values.

## Baseline CSV format

A baseline is a SISEPUEDE input data frame. That means one row per time period
and one column per model input variable, plus `region`, `time_period` and
`year` columns. The example input `tests/fixtures/example_input.csv`
shows the expected format.

When you choose a file, the *Baseline data* page checks it and lists any model
inputs it's missing. SISEPUEDE still accepts a file with missing columns, but
the sector models that need those inputs fail when you run them. For example,
Egypt baselines made before the `biomass_fix` branch are missing three columns
and break AFOLU, which also means no costs & benefits. Fix any missing columns
before you run.

## Running tests

```bash
conda activate ssp_biomass_env
pytest tests/
```

## Repository layout

```
src/sisepuede_tool/
  app.py              Shiny entry point
  config.py           paths resolved from the installed sisepuede package
  ui/                 one module per page, plus the app shell and navigation
  services/           logic with no UI (catalog, runs, costs & benefits, ...)
  models/             dataclasses shared between UI and services
  resources/          YAML configs, the NDC and LEP transformation libraries
                      (library/egypt_ndc, library/egypt_lep), Article 6 reference
                      data (article6/), CSS theme
  ref/                Egypt projects workbook
tests/                pytest suite; tests/fixtures/ has the example input and the C&B config
scripts/              helpers that regenerate metadata in resources/
docs/                 design notes
```

## Troubleshooting

- **Something failed but the app shows no error.** Errors from model runs and
  costs & benefits appear only as notifications in the app, not in the
  terminal. If a sector model fails (for example *"Error running AFOLU model:
  ... fields ... are missing"*), the warning shows up in the server log. Run
  with the `tee` command above so you have a copy.
- **Article 6 shows no credits.** Only pathways beyond the NDC are shown: run
  the LEP pathway (or your own pathway with transformations beyond the NDC).
  With the reference data, the NDC pathway itself earns about zero.
- **A run uses an old baseline.** The app keeps every baseline you've added
  for the session. Remove the old ones on *Baseline data*, or restart the app.
- **Errors when adding a baseline after reinstalling.** The `biomass_fix`
  branch of `sisepuede` is still under active development, and an upstream
  change can break the app. Commit `699ac6e` is known to work. To pin it:

  ```bash
  pip install --force-reinstall --no-deps "sisepuede @ git+https://github.com/jcsyme/sisepuede.git@699ac6e"
  ```

- **Checking which `sisepuede` commit is installed:**

  ```bash
  cat $(python -c "import sisepuede,os;print(os.path.dirname(sisepuede.__file__))")/../sisepuede-*.dist-info/direct_url.json
  ```

## License

MIT. See [LICENSE](LICENSE).
