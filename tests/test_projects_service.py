import pytest

from sisepuede_tool import config
from sisepuede_tool.services import projects_service


def test_projects_workbook_is_present():
    assert config.PROJECTS_XLSX_PATH.exists()


def test_load_projects_returns_expected_columns():
    df = projects_service.load_projects(config.PROJECTS_XLSX_PATH)
    assert list(df.columns) == projects_service.DISPLAY_COLUMNS


def test_load_projects_has_unique_nonnull_names():
    df = projects_service.load_projects(config.PROJECTS_XLSX_PATH)
    assert len(df) > 0
    assert df["Project Name"].isna().sum() == 0
    assert df["Project Name"].is_unique


def test_load_projects_cached_returns_equal_data():
    df1 = projects_service.load_projects_cached(config.PROJECTS_XLSX_PATH)
    df2 = projects_service.load_projects_cached(config.PROJECTS_XLSX_PATH)
    assert df1 is df2


def test_load_projects_missing_column_raises(tmp_path):
    import pandas as pd

    bad_path = tmp_path / "bad.xlsx"
    pd.DataFrame({"Project Name": ["x"]}).to_excel(bad_path, index=False)

    with pytest.raises(ValueError, match="missing expected column"):
        projects_service.load_projects(bad_path)
