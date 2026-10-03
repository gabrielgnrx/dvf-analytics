-- Gares et stations en projet (hors bus). Le Grand Paris Express correspond
-- aux lignes de métro 15, 16, 17 et 18 ; une gare desservie par plusieurs
-- lignes du projet (ex. 15 et 16) n'est gardée qu'une fois.

with src as (

    select
        trim(nom_arret)                                   as nom_gare,
        trim(nom_projet)                                  as projet,
        lower(trim(mode))                                 as mode,
        safe_cast(phase as int64)                         as phase,
        trim(statut)                                      as statut,
        safe_cast(latitude as float64)                    as latitude,
        safe_cast(longitude as float64)                   as longitude,
        round(safe_cast(latitude as float64), 3)          as lat_r,
        round(safe_cast(longitude as float64), 3)         as lon_r
    from {{ source('raw', 'ref_gares_projet') }}
    where lower(trim(mode)) != 'bus'

)

select
    to_hex(md5(concat(nom_gare, '|', cast(lat_r as string), '|', cast(lon_r as string)))) as gare_projet_id,
    nom_gare,
    string_agg(distinct projet, ', ' order by projet)    as projets,
    any_value(mode)                                       as mode,
    logical_or(regexp_contains(lower(projet), r'^m[ée]tro 1[5-8]')) as est_grand_paris_express,
    min(phase)                                            as phase,
    any_value(statut)                                     as statut,
    avg(latitude)                                         as latitude,
    avg(longitude)                                        as longitude,
    st_geogpoint(avg(longitude), avg(latitude))           as geog
from src
where latitude is not null and longitude is not null
group by nom_gare, lat_r, lon_r
