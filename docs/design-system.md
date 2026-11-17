# Design system: Pulse UI

*Source: Blueprint v0.1 · §5 · light theme*

A calm system for numbers people have to trust. Professional, calm and legible.
Information density over decoration. Status is always said in words and shape,
never in color alone.

## 01. Principles

- **Truth over polish.** A pretty dashboard without validated models is not done. Never show unvalidated numbers as facts.
- **Dense, not cramped.** More numbers per screen, held together by an 8 px rhythm and quiet borders.
- **Say the status.** Every state pairs a label and an icon shape with its tint: healthy, stale, invalid.
- **One definition.** Tooltips quote the metric dictionary. The UI never redefines a formula.

## 02. Color

### Neutrals

| Token | Value | Use | Contrast vs text |
|---|---|---|---|
| `color.bg` | `#FFF7F0` | App ground | 15.4 |
| `color.surface` | `#FFFFFF` | Cards, filters | 16.3 |
| `color.border` | `#F1E4D9` | Dividers (rules only) | n/a |
| `color.muted` | `#7A6558` | Labels | 4.97 |
| `color.text` | `#2B1D17` | Content | 16.3 |

### Brand and status

Each hue has a solid (v0.1 token) plus a proposed ink for chips and alerts.
The number is the contrast of ink on tint.

| Token | Solid | Ink | Ink-on-tint | Use |
|---|---|---|---|---|
| `color.primary` | `#EA6A12` | `#B84A0B` | 5.91 | Selection, links, chart line |
| `color.success` | `#16835D` | `#0F6B4A` | 5.75 | Fresh data, tests passed |
| `color.warning` | `#B7791F` | `#7A5208` | 6.26 | Delayed refresh |
| `color.danger` | `#C43D3D` | `#A33232` | 5.90 | Critical quality failure |

**Do:** use solids for fills, icons and the chart line; use the ink color for any
status text; give inputs a `#BFA896` edge so they stay visible.

**Don't:** set text in `warning` (3.64:1) or white on it; put `success` text on
`bg` (4.49:1); rely on `border` (1.15:1) as an input's only edge.

## 03. Typography

Inter, five steps, tabular numbers.

| Style | Size/line · weight | Example |
|---|---|---|
| Page title | 28/36 · 600 | Sales Overview |
| KPI | 28/34 · 600 | R$ 45.129,50 |
| Section title | 18/26 · 600 | Daily net sales |
| Body | 14/22 · 400 | Refunds adjust the original order's date… |
| Label | 12/18 · 500 | ELIGIBLE GROSS · BRL · UTC |

Numbers in KPIs and tables use `font-variant-numeric: tabular-nums`, are
right-aligned and formatted for pt-BR (`R$ 1.234,56`).

## 04. Space & shape

- `space.base` = 8 px. Scale: 4 · 8 · 16 · 24 · 32 · 56.
- 16 inside cards, 24 between cards, 56 between sections.
- Radius: 10 px inputs, 18 px cards (`radius.card`), pill chips.
- Surfaces separate with a 1 px `border` on `bg` and a soft shadow (`0 1px 3px rgba(120, 60, 20, .09)`).

## 05. Components

| Component | States | Contract |
|---|---|---|
| `MetricCard` | normal · loading · unavailable | Label, value, unit, optional delta and definition tooltip |
| `DateRangeFilter` | default · active · invalid | Date range, reset, bounds from available data |
| `ProductFilter` | all · selected · empty | Values from `dim_product`; no hardcoded categories |
| `TimeSeriesChart` | populated · empty · loading | Daily net sales, axis units, tooltip precision |
| `BreakdownTable` | populated · empty | Product/category rows, sortable metrics, totals |
| `FreshnessBadge` | healthy · stale · unknown | Last successful pipeline completion, not page load time |
| `QualityAlert` | pass · warning · failure | Clear message and accessible status without color alone |

Copy for states:

- MetricCard unavailable: `-` + "Not published · quality gate failed"
- DateRangeFilter invalid: "The end date must be on or after the start date."
- ProductFilter empty: "No products available"
- FreshnessBadge: "Healthy · [timestamp] UTC" / "Stale · [timestamp] UTC" / "Unknown · no successful run"
- QualityAlert: "Pass. All critical tests passed." / "Stale. Valid figures, but the last batch is delayed." / "Invalid. A critical check failed; results not published."

## 06. Actions & focus

A dashboard reads more than it acts: one primary action per view at most.
Variants: Primary (Apply), Secondary (Reset), Link (Docs →), each with default ·
hover · focus · disabled.

Focus ring: 2 px `primary` outline, 2 px offset, on every interactive element.
Never remove it without a replacement.

## 07. Data visualization

- Series order: 1 · Net sales (main) · 2 · Comparison series (previous period, reference only).
- Orange and deep brown differ in lightness too, so they read in grayscale and for red/green color blindness. Status colors never encode series.
- Y axis starts at zero for money; label the unit (R$) once, on the axis.
- Tooltip shows date, value with 2 decimals and the timezone.
- At most 2 series per chart; split instead of stacking more.
- Highlight one point at most.
- Every chart ships with "View as table".

## 08. Layout

- Content max width 1560 px inside a rounded panel, 28 px side padding, 64 px brand rail on the left.
- KPI strip: 5 cards in a row at 1280 px, wrapping to 2 then 1.
- Chart full width; breakdown table below it, scrolling inside its box.

## 09. Icons

16 px, 1.5 px stroke, round caps, drawn in `currentColor`. Each status has its own
shape, so it survives without color. Icon-only buttons carry an `aria-label`.

## 10. Tokens as code

`.streamlit/config.toml` (project root; used by the README quickstart)

```toml
[theme]
base = "light"
primaryColor = "#EA6A12"
backgroundColor = "#FFF7F0"
secondaryBackgroundColor = "#FFFFFF"
textColor = "#2B1D17"
font = "sans serif"
```

`dashboard/tokens.css`

```css
:root {
  --color-bg: #FFF7F0;
  --color-surface: #FFFFFF;
  --color-text: #2B1D17;
  --color-muted: #7A6558;
  --color-primary: #EA6A12;
  --color-success: #16835D;
  --color-warning: #B7791F;
  --color-danger: #C43D3D;
  --color-border: #F1E4D9;
  --radius-card: 18px;
  --space-base: 8px;
}
```

Streamlit's theme covers only base colors; status chips and cards use the CSS
variables through a small injected stylesheet, keeping formulas out of the UI layer.

## 11. Accessibility

- Keyboard-operable inputs, explicit labels, meaningful focus.
- Every chart has a tabular equivalent.
- No reliance on red/green alone.
- Text at 4.5:1 minimum; targets at 44 px.
- Locale-aware BRL formatting and an explicit timezone label.

## 12. UX acceptance

- Filtering updates every metric and chart from the same curated snapshot.
- KPI tooltips match the metric dictionary exactly.
- Empty results show explanatory states, not zeros disguised as sales.
- Warnings specify whether the data is stale or invalid.
- Usable at 1280 px; narrow widths stack cards with no page overflow.

## Screen 01 · Sales Overview

The one MVP screen. Layout, top to bottom:

1. Header: "Ember · Sales Overview" + `FreshnessBadge` + `QualityAlert` (compact).
2. Filters: start date · end date · category/product · Reset.
3. KPI strip (5 `MetricCard`): Eligible gross · Refunds · Net sales · Completed orders · Average order value.
4. `TimeSeriesChart` "Daily net sales · R$ per order date · UTC · order-cohort view" + "View as table".
5. `BreakdownTable` "Sales by category": category · eligible gross · refunds · net sales (sorted desc) · total row.
   Note under table: order counts are not summed across categories.
6. Metric definitions panel (quotes `docs/metrics.md`).
7. Pipeline status: last successful run · row counts per table · test status · link to docs.

Screen states:

| State | Behaviour |
|---|---|
| Loading skeleton | Shapes hold the layout; no numbers shown |
| No data for filter | "No completed orders match these filters" + hint + Reset filters; never `R$ 0,00` |
| Stale | Warning banner with last refresh timestamp; KPIs stay visible; badge switches to Stale |
| Critical failure | Failure banner; KPIs show `-` and are blocked. Alternative: last known-good snapshot, clearly labeled as not current, with its run timestamp |

Reference rendering: `docs/blueprint/Sales_Overview_screen.html`.
