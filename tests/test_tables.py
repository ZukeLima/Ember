"""Full-dataset sorting/searching must precede pagination."""

from streamlit.testing.v1 import AppTest

SCRIPT = """
import pandas as pd
from dashboard.tables import browsable_table
frame = pd.DataFrame({"Categoria": [f"Item {i:02d}" for i in range(26)],
                      "Vendas (R$)": [float(i) for i in range(26)]})
browsable_table(frame, key="test", filename="test.csv", money_columns=("Vendas (R$)",),
                default_sort="Vendas (R$)", descending=True)
"""


def test_pagination_and_numeric_sort_apply_to_full_dataset():
    at = AppTest.from_string(SCRIPT).run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0]["Vendas (R$)"] == 25
    assert len(at.dataframe[0].value) == 10
    at.button(key="test_next").click().run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0]["Vendas (R$)"] == 15
    at.selectbox(key="test_page").set_value(3).run()
    assert len(at.dataframe[0].value) == 6
    assert at.button(key="test_next").disabled


def test_search_resets_page_and_handles_no_matches():
    at = AppTest.from_string(SCRIPT).run()
    at.button(key="test_next").click().run()
    at.text_input(key="test_search").set_value("Item 02").run()
    assert not at.exception
    assert at.selectbox(key="test_page").value == 1
    assert len(at.dataframe[0].value) == 1
    at.text_input(key="test_search").set_value("missing").run()
    assert not at.exception
    assert len(at.dataframe) == 0
    assert any("Nenhum resultado" in info.value for info in at.info)
    assert at.button(key="test_next").disabled


def test_hidden_columns_and_page_size():
    at = AppTest.from_string(SCRIPT).run()
    at.selectbox(key="test_size").set_value(25).run()
    assert len(at.dataframe[0].value) == 25
    at.multiselect(key="test_columns").set_value(["Categoria"]).run()
    assert list(at.dataframe[0].value.columns) == ["Categoria"]
    at.multiselect(key="test_columns").set_value([]).run()
    assert not at.exception
    assert any("Escolha ao menos uma coluna" in info.value for info in at.info)
