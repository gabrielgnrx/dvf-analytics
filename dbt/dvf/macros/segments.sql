{# Macros de segmentation partagées entre dim_bien et fact_transactions,
   pour garantir que la clé calculée des deux côtés est identique. #}

{% macro classe_pieces(col_pieces, col_type) %}
    case
        when {{ col_type }} not in ('Appartement', 'Maison') then 'n/a'
        when {{ col_pieces }} is null or {{ col_pieces }} = 0 then 'Inconnu'
        when {{ col_pieces }} >= 5 then 'T5+'
        else concat('T', cast({{ col_pieces }} as string))
    end
{% endmacro %}

{% macro tranche_surface(col_surface) %}
    case
        when {{ col_surface }} is null then 'Inconnue'
        when {{ col_surface }} < 30 then '< 30 m²'
        when {{ col_surface }} < 50 then '30-50 m²'
        when {{ col_surface }} < 80 then '50-80 m²'
        when {{ col_surface }} < 120 then '80-120 m²'
        else '120 m² et +'
    end
{% endmacro %}
