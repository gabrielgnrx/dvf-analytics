-- Dimension temps au grain jour, générée (date spine) pour couvrir toute la
-- période même les jours sans transaction.

with jours as (

    select jour
    from unnest(generate_date_array(
        date('{{ var("date_debut", "2021-01-01") }}'),
        date('{{ var("date_fin", "2025-12-31") }}')
    )) as jour

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
