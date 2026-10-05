# sisepuede_tool

A [Shiny for Python](https://shiny.posit.co/py/) web app for building
decarbonization pathways with the
[SISEPUEDE](https://github.com/jcsyme/sisepuede) model. You load a baseline
dataset, put transformations together into pathways, run them, and compare
emissions and costs & benefits against business as usual.

This branch (`ndc-v1`) is the Egypt NDC version. It ships with a library of
NDC transformations and a sample Egypt baseline.

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

1. **Baseline data**: upload a baseline CSV and click *Add baseline*. To try
   the app, use the sample Egypt baseline at
   `tests/fixtures/egypt_baseline_biomass_fix.csv`.
2. **Pathways**: open a transformer, reuse an NDC transformation or create
   your own, and add it to a pathway.
3. **Run**: pick the baselines and pathways you want and run them.
4. **Results**: look at *Emissions & drivers* and *Costs & benefits*. Both
   are compared against business as usual.

The first baseline you add sets the region for the whole session. Every
baseline after that has to be for the same region.

## Baseline CSV format

A baseline is a SISEPUEDE input data frame. That means one row per time period
and one column per model input variable, plus `region`, `time_period` and
`year` columns. Use `tests/fixtures/egypt_baseline_biomass_fix.csv` as a
template.

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
  resources/          YAML configs, the NDC transformation library, CSS theme
  ref/                Egypt projects workbook
tests/                pytest suite; tests/fixtures/ has sample baselines and the C&B config
scripts/              helpers that regenerate metadata in resources/
docs/                 design notes
```

## Troubleshooting

- **Something failed but the app shows no error.** Errors from model runs and
  costs & benefits appear only as notifications in the app, not in the
  terminal. If a sector model fails (for example *"Error running AFOLU model:
  ... fields ... are missing"*), the warning shows up in the server log. Run
  with the `tee` command above so you have a copy.
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
