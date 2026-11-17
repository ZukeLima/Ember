"""Shared table controls for browsing published and hypothetical data."""

from __future__ import annotations

from math import ceil

import pandas as pd
import streamlit as st

from dashboard.format import brl


def browsable_table(
    frame: pd.DataFrame,
    *,
    key: str,
    filename: str,
    money_columns: tuple[str, ...] = (),
    date_columns: tuple[str, ...] = (),
    default_sort: str,
    descending: bool = False,
) -> None:
    """Search and sort the full table before pagination; export all matching rows."""
    search_col, sort_col = st.columns([2, 1])
    with search_col:
        query = st.text_input(
            "Buscar nesta tabela",
            placeholder="Digite uma categoria, data ou valor…",
            key=f"{key}_search",
        )
    with sort_col:
        sort = st.selectbox(
            "Ordenar por",
            list(frame.columns),
            index=list(frame.columns).index(default_sort),
            key=f"{key}_sort",
        )
    with st.expander("Ajustar visualização"):
        visible = st.multiselect(
            "Colunas visíveis",
            list(frame.columns),
            default=list(frame.columns),
            key=f"{key}_columns",
        )
        size_col, direction_col = st.columns(2)
        with size_col:
            page_size = st.selectbox("Linhas por página", [10, 25, 50], key=f"{key}_size")
        with direction_col:
            reverse = st.checkbox("Ordem decrescente", value=descending, key=f"{key}_descending")

    filtered = frame
    if query.strip():
        searchable = frame.astype(str)
        for col in money_columns:
            searchable[col] = frame[col].map(brl)
        for col in date_columns:
            searchable[col] = pd.to_datetime(frame[col]).dt.strftime("%d/%m/%Y")
        mask = searchable.apply(
            lambda col: col.str.contains(query.strip(), case=False, regex=False, na=False)
        ).any(axis=1)
        filtered = frame.loc[mask]
    filtered = filtered.sort_values(sort, ascending=not reverse, kind="stable")
    count = len(filtered)
    pages = max(1, ceil(count / page_size))
    page_key = f"{key}_page"
    signature = (query, sort, reverse, page_size, tuple(frame.columns), len(frame))
    if st.session_state.get(f"{key}_signature") != signature:
        st.session_state[page_key] = 1
        st.session_state[f"{key}_signature"] = signature
    st.session_state[page_key] = min(st.session_state.get(page_key, 1), pages)
    page = st.session_state[page_key]
    start = (page - 1) * page_size

    st.caption(
        f"{count} de {len(frame)} linhas · busca e ordenação valem para todas as páginas. "
        "Os filtros no topo do dashboard definem a base desta tabela."
    )
    if count == 0:
        st.info("Nenhum resultado. Limpe a busca ou tente outro termo.")
    elif not visible:
        st.info("Escolha ao menos uma coluna em Ajustar visualização.")
    else:
        data = filtered.iloc[start : start + page_size][visible].reset_index(drop=True)
        style = data.style.format(
            {c: lambda v: brl(v, False) for c in money_columns if c in visible}
        )
        configs = {
            c: st.column_config.DateColumn(format="DD/MM/YYYY")
            for c in date_columns
            if c in visible
        }
        st.dataframe(style, hide_index=True, width="stretch", column_config=configs)
        st.caption(
            f"Mostrando {start + 1}–{min(start + page_size, count)} de {count} linhas. "
            "Em telas pequenas, deslize a tabela para os lados ou escolha menos colunas."
        )

    def move(delta: int) -> None:
        st.session_state[page_key] = max(1, min(pages, st.session_state[page_key] + delta))

    prev_col, page_col, next_col = st.columns([1, 1.4, 1], vertical_alignment="bottom")
    with prev_col:
        st.button(
            "← Anterior",
            key=f"{key}_prev",
            on_click=move,
            args=(-1,),
            disabled=page <= 1 or not count,
            width="stretch",
        )
    with page_col:
        st.selectbox(
            "Página",
            list(range(1, pages + 1)),
            key=page_key,
            format_func=lambda p: f"{p} de {pages}",
            disabled=not count,
        )
    with next_col:
        st.button(
            "Próxima →",
            key=f"{key}_next",
            on_click=move,
            args=(1,),
            disabled=page >= pages or not count,
            width="stretch",
        )
    st.download_button(
        "Baixar resultados CSV",
        filtered.to_csv(index=False).encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        key=f"{key}_download",
        disabled=not count,
        help="Exporta todas as linhas encontradas e todas as colunas, não apenas a página atual.",
    )
