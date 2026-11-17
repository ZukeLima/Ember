{# Monetary text ("123.45") → DECIMAL(12,2). A value that cannot be parsed
   becomes NULL, which the not_null contract test then reports as critical,
   instead of crashing the build with an opaque cast error. #}
{% macro to_money(column) -%}
    try_cast({{ column }} as decimal(12, 2))
{%- endmacro %}

{# ISO-8601 UTC text ("2026-01-01T00:00:00Z") → TIMESTAMP (naive, UTC). #}
{% macro to_utc_ts(column) -%}
    try_cast(try_cast({{ column }} as timestamptz) at time zone 'UTC' as timestamp)
{%- endmacro %}
