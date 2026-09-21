# sisepuede_tool

A Shiny-for-Python GUI for designing SISEPUEDE Transformations and Strategies,
running them against one or more baseline datasets, and exploring/validating
results.

## Development setup

Requires Python 3.13 (matches `sisepuede`'s hard pin).

```bash
conda activate sisepuede   # or any 3.13 env with `sisepuede` installed
pip install -e ../sisepuede -e .[dev]
```

Run the app:

```bash
shiny run src/sisepuede_tool/app.py --reload
```

Run tests:

```bash
pytest tests/
```
