-- Dimension temps au grain jour, générée (date spine) pour couvrir toute la
-- période même les jours sans transaction.
-- Bornes dynamiques : du 1er janvier de la première année de données au
-- 31 décembre de la dernière (ou de l'année en cours). Surchargeables avec
-- --vars '{date_debut: ..., date_fin: ...}'.

with bornes as (

    select
        {% if var("date_debut", none) %}date('{{ var("date_debut") }}'){% else %}date_trunc(min(date_mutation), year){% endif %} as debut,
        {% if var("date_fin", none) %}date('{{ var("date_fin") }}'){% else %}last_day(greatest(max(date_mutation), current_date()), year){% endif %} as fin
    from {{ ref('stg_dvf__mutations') }}

),

jours as (

    select jour
    from bornes, unnest(generate_date_array(bornes.debut, bornes.fin)) as jour

)

select
    cast(format_date('%Y%m%d', jour) as int64)   as date_key,
    jour                                         as date,
    extract(year from jour)                      as annee,
    extract(quarter from jour)                   as trimestre,
    format_date('%Y-T', jour) || cast(extract(quarter from jour) as string) as annee_trimestre,
    extract(month from jour)                     as mois,
    format_date('%Y-%m', jour)                   as annee_mois,
    ['janvier','février','mars','avril','mai','juin','juillet','août',
     'septembre','octobre','novembre','décembre'][offset(extract(month from jour) - 1)] as nom_mois,
    if(extract(month from jour) <= 6, 1, 2)      as semestre,
    extract(isoweek from jour)                   as semaine_iso,
    extract(dayofweek from jour) in (1, 7)       as est_weekend
from jours
