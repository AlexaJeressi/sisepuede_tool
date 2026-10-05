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


def test_project_records_have_transformer_and_news_number():
    df = projects_service.load_project_records(config.PROJECTS_XLSX_PATH)
    assert len(df) == 53
    assert list(df.columns) == projects_service.PROJECT_COLUMNS
    row = df[df["name"] == "Obelisk Solar PV + Battery Storage (Qena)"].iloc[0]
    assert row["transformer_code"] == "TFR:ENTC:TARGET_RENEWABLE_ELEC"
    assert row["news_number"] == 17


def test_default_links_group_projects_by_transformer():
    from sisepuede_tool.services import library_service

    df = projects_service.load_project_records(config.PROJECTS_XLSX_PATH)
    items = library_service.load_library()
    links = projects_service.default_links(df, items)
    assert links["Obelisk Solar PV + Battery Storage (Qena)"] == "TX:ENTC:TARGET_RENEWABLE_ELEC_STRATEGY_NDC"
    # each project links to the NDC transformation on its transformer, if any
    by_transformer = {i.transformer_code: i.code for i in items}
    for rec in df.to_dict("records"):
        assert links[rec["name"]] == by_transformer.get(rec["transformer_code"])
    hydrogen = projects_service.projects_for_transformation("TX:ENTC:TARGET_CLEAN_HYDROGEN_STRATEGY_NDC", links)
    assert len(hydrogen) == 6
    # projects on transformers outside the NDC set stay in the portfolio, unlinked
    unlinked = [n for n, c in links.items() if c is None]
    assert len(unlinked) == 10
    assert links["Cairo Bus Rapid Transit (BRT) System"] is None


def test_unusable_library_items_are_not_linked():
    from sisepuede_tool.services import library_service

    df = projects_service.load_project_records(config.PROJECTS_XLSX_PATH)
    items = library_service.load_library()
    for item in items:
        if item.transformer_code == "TFR:ENTC:TARGET_RENEWABLE_ELEC":
            item.error = "transformer missing"
    links = projects_service.default_links(df, items)
    assert links["Obelisk Solar PV + Battery Storage (Qena)"] is None


@pytest.mark.parametrize("value,expected", [("Yes — measure", "yes"), ("Yes — named", "yes"), ("Partial", "partial"), ("No", "no"), (None, "no")])
def test_ndc_flag(value, expected):
    assert projects_service.ndc_flag(value) == expected


def test_links_round_trip_and_custom_projects():
    links = {"A": "TX:X", "B": None}
    scope = {"A": True}
    back = projects_service.links_from_dataframe(projects_service.links_to_dataframe(links, scope))
    assert back == ({"A": "TX:X", "B": None}, {"A": True, "B": False})
    rec = projects_service.make_custom_project("My plant", "TFR:ENTC:DEC_LOSSES", investment="$10M")
    assert rec["subsector"] == "ENTC" and rec["source"] == "custom"
    with pytest.raises(ValueError):
        projects_service.make_custom_project("  ")
    assert projects_service.projects_for_transformation("TX:X", links) == ["A"]
