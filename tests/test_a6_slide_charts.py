"""scripts/build_a6_slide_charts.py: the matched pair of Article 6 slide charts."""

import importlib.util
import pathlib

import pytest

from sisepuede_tool.services import article6_service as a6

_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "build_a6_slide_charts.py"


@pytest.fixture(scope="module")
def figures():
    if a6.load_ranked().empty:
        pytest.skip("no sisepuede_a6 ranked MAC file")
    spec = importlib.util.spec_from_file_location("build_a6_slide_charts", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, mod.build()


def test_the_bars_sit_in_the_same_place(figures):
    mod, (f1, f2) = figures
    for f in (f1, f2):
        assert (f.layout.width, f.layout.height) == (mod.W, mod.H)
        assert (f.layout.margin.l, f.layout.margin.r, f.layout.margin.t, f.layout.margin.b) == (mod.L, mod.R, mod.T, mod.B)
        assert f.layout.margin.autoexpand is False and f.layout.yaxis.autorange is False
    assert tuple(f1.layout.yaxis.range) == tuple(f2.layout.yaxis.range)


def test_every_sector_and_transformation_in_the_legends(figures):
    _, (f1, f2) = figures
    df = a6.load_ranked()
    live = df.groupby([a6.FIELD_GROUP, a6.FIELD_KERNEL])["value_musd"].transform(lambda v: v.abs().max()) > 1e-9
    pairs = df[live].drop_duplicates([a6.FIELD_GROUP, a6.FIELD_KERNEL])
    # a legend swatch per sector / (sector, transformation)
    assert len(f1.layout.shapes) - _band(f1) == pairs[a6.FIELD_GROUP].nunique()
    assert len(f2.layout.shapes) - _band(f2) == len(pairs)


def _band(fig) -> int:
    """Shapes that are not legend swatches (the grey band after the NDC2.0 targets)."""
    return sum(1 for s in fig.layout.shapes if s.type != "rect" or s.xref != "paper")
