"""Ember · Sales Overview (Screen 01).

Presentation only (ADR-002): reads the published marts and the run artifact.
States: loading · no data for filter · stale · critical failure.
Two views of the same screen: Desktop (default) and Mobile (`?view=mobile`).
"""

from __future__ import annotations

import secrets
import sys
from datetime import date, timedelta
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # `streamlit run dashboard/app.py` from the repo root

from dashboard import data as dp  # noqa: E402
from dashboard.format import brl, integer, pct  # noqa: E402
from dashboard.scenarios import STRATEGIES, simulate_sales  # noqa: E402

DEFINITIONS = {
    "Eligible gross": "Sum(quantity × unit_price) for order items whose latest order status is "
    "completed. Pending and cancelled are excluded.",
    "Refunds": "Sum of successful refunds linked to eligible completed order items. "
    "Pending and failed refunds are excluded.",
    "Net sales": "eligible_gross − refunded_amount, 2 decimal places.",
    "Completed orders": "Count of distinct completed order_id. With a product or category "
    "filter: distinct completed orders containing the selected products.",
    "Average order value": "net_sales / completed_orders; empty when there are no completed "
    "orders.",
}
# Formulas rendered as <code> in the definitions card (text itself is untouched).
CODE_SNIPPETS = (
    "quantity × unit_price",
    "eligible_gross − refunded_amount",
    "net_sales / completed_orders",
    "order_id",
)
METRICS_DOC_URL = "docs/metrics.md"  # point to the repository file when published
STRATEGY_LABELS = {
    "Manter operação": "Keep operations",
    "Campanha promocional": "Promotional campaign",
    "Retenção de clientes": "Customer retention",
    "Ajuste de preço": "Price adjustment",
}
CHART_NET = "#F97316"  # net sales (orange)
CHART_REFUND = "#7C2D12"  # refunds (deep brown)
CHART_GROSS = "#F5B83D"  # eligible gross (amber)
CAT_COLORS = ["#F97316", "#F5B83D", "#C2410C", "#F58BA3", "#FDBA8C", "#A8745A"]
CHART_GRID = "#F1E4D9"
CHART_MUTED = "#7A6558"
CHART_TEXT = "#2B1D17"
MONEY_AXIS = "replace(format(datum.value, ',.0f'), ',', '.')"

PULSE_ICON = (HERE / "assets" / "ember.svg").read_text()
st.set_page_config(page_title="Ember · Sales Overview", page_icon=PULSE_ICON, layout="wide")
st.markdown(f"<style>{(HERE / 'tokens.css').read_text()}</style>", unsafe_allow_html=True)

# View: desktop (default) or a phone-sized layout. `?view=mobile` opens the mobile one directly.
if "view" not in st.session_state:
    st.session_state["view"] = (
        "Mobile" if str(st.query_params.get("view", "")).lower() == "mobile" else "Desktop"
    )
mobile = st.session_state.get("view") == "Mobile"
if mobile:
    st.markdown(
        "<style>"
        '[data-testid="stMainBlockContainer"]{max-width:430px !important;'
        "padding:16px 16px 32px !important;background:var(--color-panel);"
        "border:none;border-radius:28px;margin:16px auto;"
        "box-shadow:0 8px 30px rgba(120,60,20,.15)}"
        "table.dp-table{font-size:12.5px}"
        "table.dp-table td,table.dp-table th{padding:4px 6px}"
        ".dp-chips{justify-content:flex-start !important}"
        ".dp-strip{grid-template-columns:repeat(2,minmax(0,1fr)) !important}"
        ".dp-kpi:last-child:nth-child(odd){grid-column:span 2}"
        "</style>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- components


def chip(kind: str, text: str) -> str:
    shape = {
        "healthy": "●",
        "pass": "●",
        "stale": "▲",
        "warning": "▲",
        "failure": "■",
        "unknown": "○",
    }[kind]
    return f'<span class="dp-chip {kind}" role="status">{shape} {text}</span>'


def metric_card(
    label: str,
    value: str | None,
    unit: str | None,
    sub: str,
    definition: str,
    *,
    sub_kind: str = "",
    dot: str = "#A8745A",
    key: bool = False,
    unavailable: bool = False,
) -> str:
    cls = "dp-kpi" + (" key" if key else "") + (" dp-unavailable" if unavailable else "")
    unit_html = f'<span class="dp-unit">{unit}</span>' if (unit and not unavailable) else ""
    v = "-" if unavailable or value is None else value
    sub_html = f'<div class="dp-sub {sub_kind}">{sub}</div>' if sub else ""
    return (
        f'<div class="{cls}" title="{escape(definition, quote=True)}" tabindex="0" '
        f'role="group" aria-label="{escape(label)}: {escape(v)}. {escape(definition, quote=True)}">'
        f'<div class="dp-label"><span><i class="dp-dot" style="background:{dot}"></i>{label}</span>'
        f'<span aria-hidden="true">ⓘ</span></div>'
        f'<div class="dp-value">{unit_html}{v}</div>{sub_html}</div>'
    )


def quality_alert(kind: str, title: str, body: str) -> None:
    st.markdown(
        f'<div class="dp-alert {kind}" role="alert"><strong>{title}</strong> {body}</div>',
        unsafe_allow_html=True,
    )


def fmt_ts(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") + " UTC" if dt else "[no successful run]"


def html_table(headers: list[str], rows: list[list[str]], total: list[str] | None = None) -> str:
    head = "".join(f'<th scope="col">{escape(h)}</th>' for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row) + "</tr>" for row in rows)
    foot = (
        '<tr class="total">' + "".join(f"<td>{escape(c)}</td>" for c in total) + "</tr>"
        if total
        else ""
    )
    return (
        '<div class="dp-table-wrap"><table class="dp-table">'
        f"<thead><tr>{head}</tr></thead><tbody>{body}{foot}</tbody></table></div>"
    )


def definition_html(text: str) -> str:
    out = escape(text)
    for snippet in CODE_SNIPPETS:
        out = out.replace(escape(snippet), f"<code>{escape(snippet)}</code>")
    return out


def test_status_label(raw: str | None) -> str:
    if not raw:
        return "unknown"
    return "all critical tests passed" if raw == "all_critical_passed" else raw.replace("_", " ")


def card_header(title: str, caption: str, stacked: bool = False) -> None:
    if mobile or stacked:
        st.subheader(title)
        st.markdown(f'<div class="dp-caption">{caption}</div>', unsafe_allow_html=True)
        return
    left, right = st.columns([2, 3], vertical_alignment="center")
    left.subheader(title)
    right.markdown(f'<div class="dp-caption right">{caption}</div>', unsafe_allow_html=True)


def style_chart(chart: alt.Chart | alt.LayerChart, height: int) -> alt.Chart | alt.LayerChart:
    return (
        chart.properties(height=height)
        .configure(background="#FFFFFF")
        .configure_axis(
            labelColor=CHART_MUTED,
            labelFontSize=12,
            gridColor=CHART_GRID,
            domain=False,
            tickColor=CHART_GRID,
        )
        .configure_legend(labelColor=CHART_MUTED, labelFontSize=12, orient="bottom", title=None)
        .configure_view(strokeWidth=0)
    )


# --------------------------------------------------------------------------- header + status

status = dp.load_status()

if status.freshness == "healthy":
    chip_fresh = chip(
        "healthy",
        f"Healthy · last successful run {fmt_ts(status.last_successful_run_at)}",
    )
elif status.freshness == "stale":
    chip_fresh = chip("stale", f"Stale · {fmt_ts(status.last_successful_run_at)}")
else:
    chip_fresh = chip("unknown", "Unknown · no successful run")
chip_quality = (
    chip("pass", "Quality: all critical tests passed")
    if status.quality == "pass"
    else chip("warning", "Quality: passed with warnings")
    if status.quality == "warning"
    else chip("failure", "Quality: critical check failed")
    if status.quality == "failure"
    else chip("unknown", "Quality: unknown")
)
brand_html = (
    '<div class="dp-brand">'
    + PULSE_ICON.replace("<svg ", '<svg aria-hidden="true" width="16" height="16" ')
    + "<span>Ember</span></div>"
)

if not mobile:
    st.markdown(
        '<div class="dp-rail">'
        + PULSE_ICON.replace("<svg ", '<svg aria-hidden="true" width="22" height="22" ')
        + "</div>",
        unsafe_allow_html=True,
    )
if mobile:
    with st.container(key="mhead"):
        m_col, t_col = st.columns([3, 5], vertical_alignment="center")
        menu_box = m_col.popover("Menu", icon=":material/menu:", width="stretch", key="menu")
        with t_col:
            st.markdown(brand_html, unsafe_allow_html=True)
            st.title("Sales Overview")
    st.markdown(
        f'<div class="dp-chips">{chip_fresh}{chip_quality}</div>',
        unsafe_allow_html=True,
    )
else:
    h_title, h_chips, h_view = st.columns([4, 6, 2], vertical_alignment="bottom")
    with h_title:
        st.markdown(brand_html, unsafe_allow_html=True)
        st.title("Sales Overview")
    with h_chips:
        st.markdown(
            f'<div class="dp-chips">{chip_fresh}{chip_quality}</div>',
            unsafe_allow_html=True,
        )
    with h_view:
        st.segmented_control(
            "View",
            ["Desktop", "Mobile"],
            key="view",
            label_visibility="collapsed",
            width="stretch",
        )

critical = status.quality == "failure"
pub = dp.published_path()
have_published = pub.exists()

if critical:
    quality_alert(
        "failure",
        "■ Failure · invalid data.",
        "A critical check failed, so newly computed results are not published. "
        + (
            f"Showing the last known-good snapshot from {fmt_ts(status.last_successful_run_at)}, "
            "which is <em>not current</em>."
            if have_published
            else "No previous snapshot is available."
        ),
    )
    with st.expander("Failing checks", expanded=True):
        for f in status.failures:
            st.markdown(f"- `{f['test']}`: {f.get('failures')} offending row(s)")
elif status.freshness == "stale":
    quality_alert(
        "warning",
        "▲ Warning · stale data.",
        f"Last successful refresh was {fmt_ts(status.last_successful_run_at)}. "
        "Figures passed all tests but may miss newer orders.",
    )
elif status.quality == "warning":
    quality_alert(
        "warning",
        "▲ Warning.",
        "Valid figures; some non-critical checks reported warnings.",
    )

if not have_published:
    st.markdown(
        '<div class="dp-empty"><strong>Nothing published yet</strong>'
        "Run <code>ember build --src data/generated/clean</code> to produce the first snapshot."
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

# --------------------------------------------------------------------------- filters

con = dp.connect(pub)
bounds = dp.bounds(con)
cats = dp.categories(con)

if bounds is None:
    lo = hi = date.today()
else:
    lo, hi = bounds

if "start" not in st.session_state or st.session_state.get("_data_bounds") != (lo, hi):
    st.session_state.update({"start": lo, "end": hi, "category": "All", "product": "All"})
    st.session_state["_data_bounds"] = (lo, hi)


def reset() -> None:
    st.session_state.update({"start": lo, "end": hi, "category": "All", "product": "All"})


def filter_widgets() -> tuple[date, date, str, str]:
    """Same four filters + Reset; one row on desktop, stacked in the mobile drawer."""
    if mobile:
        d1, d2 = st.columns(2)
        start_ = d1.date_input(
            "Start date", min_value=lo, max_value=hi, key="start", format="DD/MM/YYYY"
        )
        end_ = d2.date_input("End date", min_value=lo, max_value=hi, key="end", format="DD/MM/YYYY")
        c3 = c4 = c5 = st.container()
    else:
        c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.4, 1.8, 0.7], vertical_alignment="bottom")
        start_ = c1.date_input(
            "Start date", min_value=lo, max_value=hi, key="start", format="DD/MM/YYYY"
        )
        end_ = c2.date_input("End date", min_value=lo, max_value=hi, key="end", format="DD/MM/YYYY")
    with c3:
        category_ = st.selectbox(
            "Category",
            ["All", *cats],
            key="category",
            disabled=not cats,
            placeholder="No products available",
        )
    with c4:
        prods = dp.products(con, None if category_ == "All" else category_)
        if st.session_state.get("product", "All") not in [
            "All",
            *(pid for pid, _ in prods),
        ]:
            st.session_state["product"] = "All"
        prod_labels = {pid: f"{name} ({pid})" for pid, name in prods}
        product_ = st.selectbox(
            "Product",
            ["All", *prod_labels.keys()],
            key="product",
            format_func=lambda k: "All products" if k == "All" else prod_labels.get(k, k),
            disabled=not prods,
        )
    with c5:
        st.button("Reset", on_click=reset, width="stretch")
    return start_, end_, category_, product_


if mobile:
    with menu_box:
        st.markdown('<div class="dp-menu-title">Filters</div>', unsafe_allow_html=True)
        start, end, category, product = filter_widgets()
else:
    with st.container(border=True, key="card-filters"):
        start, end, category, product = filter_widgets()

if end < start:
    st.error("The end date must be on or after the start date.")
    con.close()
    st.stop()

if mobile:
    _names = dict(dp.products(con, None))
    _cat_pill = escape(category) if category != "All" else "All categories"
    _prod_pill = escape(_names.get(product, product)) if product != "All" else "All products"
    st.markdown(
        '<div class="dp-pills">'
        f"<span>{start:%d/%m/%Y} – {end:%d/%m/%Y}</span>"
        f"<span>{_cat_pill}</span>"
        f"<span>{_prod_pill}</span>"
        "</div>",
        unsafe_allow_html=True,
    )

filters = dp.Filters(
    start=start,
    end=end,
    category=None if category == "All" else category,
    product_id=None if product == "All" else product,
)
unfiltered = (
    filters.start == lo and filters.end == hi and not filters.category and not filters.product_id
)

# --------------------------------------------------------------------------- load (skeleton)

skeleton = st.empty()
skeleton.markdown(
    '<div class="dp-skeleton" aria-busy="true" aria-label="Loading curated snapshot">'
    + "<div></div>" * 5
    + '<div class="wide"></div></div>',
    unsafe_allow_html=True,
)
with st.spinner("Loading curated snapshot…"):
    k = dp.kpi_total(con) if unfiltered else dp.kpis(con, filters)
    daily = dp.daily(con, filters)
    table = dp.breakdown(con, filters)

    # Previous period of the same length, via the already-tested kpis() query.
    # Only shown when it fits entirely inside the published date range.
    span = (filters.end - filters.start).days + 1
    prev_end = filters.start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    prev_net = None
    if prev_start >= lo:
        prev_net = dp.kpis(
            con,
            dp.Filters(
                start=prev_start,
                end=prev_end,
                category=filters.category,
                product_id=filters.product_id,
            ),
        )["net_sales"]
skeleton.empty()

# --------------------------------------------------------------------------- empty state

if daily.empty:
    st.markdown(
        '<div class="dp-empty"><strong>No completed orders match these filters</strong>'
        "Widen the date range or choose All products. Nothing is shown as R$ 0,00 because "
        "no sales were recorded for this selection.</div>",
        unsafe_allow_html=True,
    )
    st.button("Reset filters", on_click=reset, key="reset_empty")
    con.close()
    st.stop()

# --------------------------------------------------------------------------- data views

daily_view = daily.assign(
    order_date=pd.to_datetime(daily["order_date"]),
    eligible_gross=daily["eligible_gross"].astype(float),
    refunded_amount=daily["refunded_amount"].astype(float),
    net_sales=daily["net_sales"].astype(float),
    net_sales_display=daily["net_sales"].map(brl),
)
daily_view["is_peak"] = daily_view["net_sales"] == daily_view["net_sales"].max()
cat_view = table.assign(
    net_sales=table["net_sales"].astype(float),
    category_label=table["category"].astype(str).str.capitalize(),
    net_sales_display=table["net_sales"].map(brl),
).sort_values("net_sales", ascending=False)
cat_color = {
    c: CAT_COLORS[i % len(CAT_COLORS)] for i, c in enumerate(cat_view["category"].astype(str))
}

# --------------------------------------------------------------------------- KPIs

net_sub, net_kind = "", ""
if prev_net and float(prev_net) > 0:
    change = (float(k["net_sales"]) - float(prev_net)) / float(prev_net) * 100
    net_sub = f"{pct(change)} vs previous period"
    net_kind = "up" if change > 0 else "down" if change < 0 else ""
note = "not current · last known-good" if critical else ""
cards = [
    (
        "Eligible gross",
        brl(k["eligible_gross"], False),
        "R$",
        note,
        "",
        CHART_GROSS,
        False,
    ),
    ("Refunds", brl(k["refunded_amount"], False), "R$", note, "", CHART_REFUND, False),
    (
        "Net sales",
        brl(k["net_sales"], False),
        "R$",
        note or net_sub,
        "" if note else net_kind,
        CHART_NET,
        True,
    ),
    (
        "Completed orders",
        integer(k["completed_orders"]),
        None,
        note,
        "",
        "#FDBA8C",
        False,
    ),
    (
        "Average order value",
        brl(k["average_order_value"], False),
        "R$",
        note,
        "",
        "#F4845F",
        False,
    ),
]
st.markdown(
    '<div class="dp-strip">'
    + "".join(
        metric_card(
            label,
            value,
            unit if value != "-" else None,
            sub,
            DEFINITIONS[label],
            sub_kind=kind,
            dot=dot,
            key=key,
            unavailable=value == "-",
        )
        for label, value, unit, sub, kind, dot, key in cards
    )
    + "</div>",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- cards


@st.dialog("Daily net sales · table", width="large")
def daily_table_dialog() -> None:
    rows = [
        [
            f"{r.order_date:%d/%m/%Y}",
            brl(r.eligible_gross, False),
            brl(r.refunded_amount, False),
            brl(r.net_sales, False),
        ]
        for r in daily_view.sort_values("order_date", ascending=False).itertuples()
    ]
    st.markdown(
        '<div class="dp-caption">R$ · order date in UTC · order-cohort view</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        html_table(["Date (UTC)", "Eligible gross", "Refunds", "Net sales"], rows),
        unsafe_allow_html=True,
    )
    st.download_button(
        "Download CSV",
        daily.to_csv(index=False).encode("utf-8-sig"),
        file_name="ember-daily-net-sales.csv",
        mime="text/csv",
        key="dl_daily",
    )


def head_with_link(title: str, caption: str) -> object:
    """Card header: title + caption on the left, one text-link slot on the right."""
    title_col, link_col = st.columns([1, 1] if mobile else [6, 2], vertical_alignment="top")
    with title_col:
        st.subheader(title)
        st.markdown(f'<div class="dp-caption">{caption}</div>', unsafe_allow_html=True)
    return link_col


def trend_card() -> None:
    with st.container(border=True, key="card-trend"):
        with head_with_link("Daily net sales", "R$ per order date · UTC · order-cohort view"):
            if st.button("View as table", key="view_table"):
                daily_table_dialog()
        base = alt.Chart(daily_view).encode(
            x=alt.X(
                "order_date:T",
                title=None,
                axis=alt.Axis(format="%d/%m", tickCount=5 if mobile else 6, grid=False),
            ),
            y=alt.Y(
                "net_sales:Q",
                title=None,
                scale=alt.Scale(
                    domainMin=0,
                    domainMax=max(float(daily_view["net_sales"].max()) * 1.18, 1),
                ),
                axis=alt.Axis(labelExpr=MONEY_AXIS, tickCount=4),
            ),
            tooltip=[
                alt.Tooltip("order_date:T", title="Order date (UTC)", format="%d/%m/%Y"),
                alt.Tooltip("net_sales_display:N", title="Net sales"),
            ],
        )
        area = base.mark_area(
            interpolate="monotone",
            line=False,
            color=alt.Gradient(
                gradient="linear",
                stops=[
                    alt.GradientStop(color="rgba(249,115,22,0.24)", offset=0),
                    alt.GradientStop(color="rgba(249,115,22,0.0)", offset=1),
                ],
                x1=1,
                x2=1,
                y1=0,
                y2=1,
            ),
        )
        line = base.mark_line(color=CHART_NET, strokeWidth=2.5, interpolate="monotone")
        hover = base.mark_point(opacity=0, size=260)
        peak_dot = base.transform_filter("datum.is_peak").mark_point(
            filled=True,
            fill=CHART_REFUND,
            stroke="#FFFFFF",
            strokeWidth=2,
            size=130,
            opacity=1,
        )
        peak_label = (
            base.transform_filter("datum.is_peak")
            .mark_text(dy=-16, fontSize=12, fontWeight=700, color=CHART_TEXT)
            .encode(text=alt.Text("net_sales_display:N"))
        )
        st.altair_chart(
            style_chart(area + line + hover + peak_dot + peak_label, 190 if mobile else 170),
            width="stretch",
            theme=None,
        )


def donut_card() -> None:
    with st.container(border=True, key="card-donut"):
        st.subheader("Net sales by category")
        st.markdown(
            '<div class="dp-caption">R$ · share of selected period</div>',
            unsafe_allow_html=True,
        )
        chart_col, legend_col = st.columns([1, 1.25], vertical_alignment="center")
        order = list(cat_view["category"].astype(str))
        arc = (
            alt.Chart(cat_view.assign(category=cat_view["category"].astype(str)))
            .mark_arc(
                innerRadius=44 if mobile else 50,
                outerRadius=72 if mobile else 82,
                stroke="#FFFFFF",
                strokeWidth=2,
            )
            .encode(
                theta=alt.Theta("net_sales:Q", stack=True),
                color=alt.Color(
                    "category:N",
                    sort=order,
                    scale=alt.Scale(domain=order, range=[cat_color[c] for c in order]),
                    legend=None,
                ),
                order=alt.Order("net_sales:Q", sort="descending"),
                tooltip=[
                    alt.Tooltip("category_label:N", title="Category"),
                    alt.Tooltip("net_sales_display:N", title="Net sales"),
                ],
            )
        )
        with chart_col:
            st.altair_chart(
                arc.properties(width=150 if mobile else 170, height=150 if mobile else 170)
                .configure(background="#FFFFFF")
                .configure_view(strokeWidth=0),
                width="content",
                theme=None,
            )
        with legend_col:
            st.markdown(
                '<div class="dp-legend">'
                + "".join(
                    f'<div><span><i class="dp-dot" style="background:{cat_color[str(r.category)]}">'
                    f"</i>{escape(str(r.category_label))}</span><b>{r.net_sales_display}</b></div>"
                    for r in cat_view.itertuples()
                )
                + "</div>",
                unsafe_allow_html=True,
            )


def composition_card() -> None:
    """Each day's eligible gross split into what stayed (net) and what was refunded."""
    parts = daily_view.melt(
        id_vars="order_date",
        value_vars=["net_sales", "refunded_amount"],
        var_name="part",
        value_name="value",
    )
    parts["part"] = parts["part"].map({"net_sales": "Net sales", "refunded_amount": "Refunds"})
    parts["display"] = parts["value"].map(brl)
    with st.container(border=True, key="card-composition"):
        st.subheader("Net sales vs refunds")
        st.markdown(
            '<div class="dp-caption">R$ per order date · UTC · stacked = eligible gross</div>',
            unsafe_allow_html=True,
        )
        stack = (
            alt.Chart(parts)
            .mark_bar(size=5 if mobile else 7, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X(
                    "order_date:T",
                    title=None,
                    axis=alt.Axis(format="%d/%m", tickCount=5 if mobile else 6, grid=False),
                ),
                y=alt.Y(
                    "value:Q",
                    title=None,
                    stack="zero",
                    axis=alt.Axis(labelExpr=MONEY_AXIS, tickCount=3),
                ),
                color=alt.Color(
                    "part:N",
                    scale=alt.Scale(
                        domain=["Net sales", "Refunds"], range=[CHART_NET, CHART_REFUND]
                    ),
                ),
                order=alt.Order("part:N", sort="descending"),
                tooltip=[
                    alt.Tooltip("order_date:T", title="Order date (UTC)", format="%d/%m/%Y"),
                    alt.Tooltip("part:N", title="Component"),
                    alt.Tooltip("display:N", title="Value"),
                ],
            )
        )
        st.altair_chart(style_chart(stack, 175 if mobile else 150), width="stretch", theme=None)


def breakdown_card() -> None:
    top = float(cat_view["net_sales"].max()) or 1.0
    body = "".join(
        f'<tr><td><i class="dp-dot" style="background:{cat_color[str(r.category)]}"></i>'
        f"{escape(str(r.category))}</td><td>{brl(r.eligible_gross, False)}</td>"
        f"<td>{brl(r.refunded_amount, False)}</td>"
        '<td><div class="dp-cell">'
        f'<span class="dp-bar" style="width:{r.net_sales / top * 100:.0f}%"></span>'
        f'<span class="dp-num">{brl(r.net_sales, False)}</span></div></td></tr>'
        for r in cat_view.itertuples()
    )
    total = (
        '<tr class="total"><td>Total</td>'
        f"<td>{brl(cat_view['eligible_gross'].sum(), False)}</td>"
        f"<td>{brl(cat_view['refunded_amount'].sum(), False)}</td>"
        f"<td>{brl(cat_view['net_sales'].sum(), False)}</td></tr>"
    )
    with st.container(border=True, key="card-table"):
        link = head_with_link(
            "Sales by category",
            "R$ · Order counts are not summed across categories, because one order can contain "
            "items from several of them.",
        )
        with link:
            st.download_button(
                "Download CSV",
                table.to_csv(index=False).encode("utf-8-sig"),
                file_name="ember-sales-by-category.csv",
                mime="text/csv",
                key="dl_category",
            )
        st.markdown(
            '<div class="dp-table-wrap"><table class="dp-table"><thead><tr>'
            '<th scope="col">Category</th><th scope="col">Eligible gross</th>'
            '<th scope="col">Refunds</th><th scope="col">Net sales ↓</th></tr></thead>'
            f"<tbody>{body}{total}</tbody></table></div>",
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------- definitions + status


def definitions_card() -> None:
    with st.container(key="card-defs"):
        items = "".join(
            f"<li><strong>{escape(name)}:</strong> {definition_html(text)}</li>"
            for name, text in DEFINITIONS.items()
        )
        st.markdown(f'<ul class="dp-defs">{items}</ul>', unsafe_allow_html=True)
        st.markdown(
            '<div class="dp-note">Order-cohort reporting: refunds adjust the original order\'s '
            "date, so past days can change when late refunds arrive.</div>",
            unsafe_allow_html=True,
        )


def pipeline_card() -> None:
    with st.container(key="card-pipeline"):
        counts = " · ".join(f"{t} {n}" for t, n in status.row_counts.items()) or "unavailable"
        last_run = fmt_ts(status.last_successful_run_at)
        st.markdown(
            '<ul class="dp-defs">'
            f"<li><strong>Last successful run:</strong> {last_run}</li>"
            f"<li><strong>Row counts:</strong> {escape(counts)}</li>"
            f"<li><strong>Test status:</strong> {test_status_label(status.test_status)}</li>"
            "</ul>"
            f'<div class="dp-link"><a href="{escape(METRICS_DOC_URL)}" target="_blank" '
            'rel="noopener">Read the metric documentation →</a></div>',
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------- what-if (hypothetical)


def whatif_section() -> None:
    with st.container(key="card-whatif"):
        st.caption(
            "A simulation built from the selected period. Percentages are assumptions, not "
            "estimated effects; costs and profit are not modelled. BRL · UTC dates."
        )
        if critical:
            st.warning("The base shown is the last known-good snapshot and is not current.")
        if not k["completed_orders"] or not k["eligible_gross"]:
            st.info("Select a period with completed orders and sales to simulate.")
            return

        def apply_strategy() -> None:
            volume_, price_, discount_ = STRATEGIES[st.session_state["strategy"]]
            st.session_state.update(
                scenario_volume=volume_,
                scenario_price=price_,
                scenario_discount=discount_,
            )

        def randomize_scenario() -> None:
            st.session_state["scenario_seed"] = secrets.randbelow(1_000_000)

        for key, value in {
            "scenario_volume": 0,
            "scenario_price": 0,
            "scenario_discount": 0,
            "scenario_seed": 7,
        }.items():
            st.session_state.setdefault(key, value)
        st.selectbox(
            "Starting strategy",
            list(STRATEGIES),
            key="strategy",
            on_change=apply_strategy,
            format_func=lambda s: STRATEGY_LABELS.get(s, s),
        )
        sc = [st.container()] * 3 if mobile else st.columns(3)
        with sc[0]:
            horizon = st.selectbox("Days to simulate", [30, 60, 90, 180], index=2)
            volume = st.slider("Order volume change (%)", -100, 200, key="scenario_volume")
        with sc[1]:
            price = st.slider("Price change (%)", -50, 100, key="scenario_price")
            discount = st.slider("Discount on adjusted price (%)", 0, 70, key="scenario_discount")
        with sc[2]:
            base_rate = float(k["refunded_amount"] / k["eligible_gross"]) * 100
            refund_rate = st.number_input(
                "Refunds over gross sales (%)",
                min_value=0.0,
                max_value=100.0,
                value=base_rate,
                step=0.1,
                format="%.2f",
            )
            variability = st.slider("Daily random variation (%)", 0, 100, value=25)
        st.button("Draw another scenario", on_click=randomize_scenario)
        scenario = simulate_sales(
            start=filters.end + timedelta(days=1),
            days=horizon,
            baseline_days=(filters.end - filters.start).days + 1,
            completed_orders=int(k["completed_orders"]),
            eligible_gross=float(k["eligible_gross"]),
            refunded_amount=float(k["refunded_amount"]),
            volume_change=volume,
            price_change=price,
            discount=discount,
            refund_rate=refund_rate,
            variability=variability,
            seed=int(st.session_state["scenario_seed"]),
        )
        reference = scenario["reference_net_sales"].sum()
        projected = scenario["net_sales"].sum()
        m = [st.container()] * 3 if mobile else st.columns(3)
        m[0].metric("Simulated reference · no strategy", brl(reference))
        m[1].metric("Simulated net sales", brl(projected), delta=brl(projected - reference))
        m[2].metric("Simulated orders", integer(scenario["completed_orders"].sum()))
        plot = scenario.melt(
            id_vars="order_date",
            value_vars=["reference_net_sales", "net_sales"],
            var_name="series",
            value_name="value",
        )
        plot["series"] = plot["series"].map(
            {
                "reference_net_sales": "Simulated reference",
                "net_sales": "Simulated strategy",
            }
        )
        plot["order_date"] = pd.to_datetime(plot["order_date"])
        plot["display_value"] = plot["value"].map(brl)
        sim = alt.Chart(plot).encode(
            x=alt.X(
                "order_date:T",
                title=None,
                axis=alt.Axis(format="%d/%m", tickCount=6, grid=False),
            ),
            y=alt.Y(
                "value:Q",
                title=None,
                scale=alt.Scale(domainMin=0, domainMax=max(float(plot["value"].max()) * 1.15, 1)),
                axis=alt.Axis(labelExpr=MONEY_AXIS),
            ),
            color=alt.Color(
                "series:N",
                scale=alt.Scale(
                    domain=["Simulated reference", "Simulated strategy"],
                    range=[CHART_NET, CHART_REFUND],
                ),
            ),
            strokeDash=alt.StrokeDash("series:N", legend=None),
            tooltip=[
                alt.Tooltip("order_date:T", title="Date (UTC)", format="%d/%m/%Y"),
                alt.Tooltip("series:N", title="Scenario"),
                alt.Tooltip("display_value:N", title="Net sales"),
            ],
        )
        st.altair_chart(style_chart(sim.mark_line(), 260), width="stretch", theme=None)
        st.caption(
            f"Base: {filters.start:%d/%m/%Y} to {filters.end:%d/%m/%Y} · "
            f"Simulation: {scenario.iloc[0]['order_date']:%d/%m/%Y} to "
            f"{scenario.iloc[-1]['order_date']:%d/%m/%Y}. Reference and strategy share the same "
            "daily variation."
        )


# --------------------------------------------------------------------------- layout


@st.dialog("Metric definitions", width="large")
def definitions_dialog() -> None:
    definitions_card()


@st.dialog("Pipeline status", width="large")
def pipeline_dialog() -> None:
    pipeline_card()


@st.dialog("What-if scenario · hypothetical, not published data", width="large")
def whatif_dialog() -> None:
    whatif_section()


if mobile:
    trend_card()
    donut_card()
    breakdown_card()
    composition_card()
    with menu_box:
        st.divider()
        st.markdown('<div class="dp-menu-title">View</div>', unsafe_allow_html=True)
        st.segmented_control(
            "View",
            ["Desktop", "Mobile"],
            key="view",
            label_visibility="collapsed",
            width="stretch",
        )
        st.markdown('<div class="dp-menu-title">Details</div>', unsafe_allow_html=True)
        open_defs = st.button("Metric definitions", key="open_defs", width="stretch")
        open_pipe = st.button("Pipeline status", key="open_pipeline", width="stretch")
        open_what = st.button("What-if scenario (hypothetical)", key="open_whatif", width="stretch")
    if open_defs:
        definitions_dialog()
    elif open_pipe:
        pipeline_dialog()
    elif open_what:
        whatif_dialog()
else:
    row1_l, row1_r = st.columns([8, 4])
    with row1_l:
        trend_card()
    with row1_r:
        donut_card()
    row2_l, row2_r = st.columns([8, 4])
    with row2_l:
        breakdown_card()
    with row2_r:
        composition_card()
    f1, f2, f3, _ = st.columns([2, 2, 3, 7])
    if f1.button("Metric definitions", key="open_defs"):
        definitions_dialog()
    if f2.button("Pipeline status", key="open_pipeline"):
        pipeline_dialog()
    if f3.button("What-if scenario (hypothetical)", key="open_whatif"):
        whatif_dialog()

con.close()
