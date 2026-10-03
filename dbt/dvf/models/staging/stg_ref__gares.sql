-- Gares en service, une ligne par gare physique (la source répète la gare pour
-- chaque ligne qui la dessert). "Transport lourd" = métro, RER, train, VAL :
-- le tram est gardé à part car son effet sur les prix est plus local.

with src as (

    select
        trim(nom_gares)                                   as nom_gare,
        upper(trim(mode))                                 as mode,
        trim(res_com)                                     as ligne,
        safe_cast(latitude as float64)                    as latitude,
        safe_cast(longitude as float64)                   as longitude,
        round(safe_cast(latitude as float64), 3)          as lat_r,
        round(safe_cast(longitude as float64), 3)         as lon_r
    from {{ source('raw', 'ref_gares') }}

)

select
    to_hex(md5(concat(nom_gare, '|', cast(lat_r as string), '|', cast(lon_r as string)))) as gare_id,
    nom_gare,
    -- mode "le plus lourd" desservant la gare
    case
        when logical_or(mode = 'RER') then 'RER'
        when logical_or(mode = 'METRO') then 'METRO'
        when logical_or(mode = 'TRAIN') then 'TRAIN'
        when logical_or(mode = 'VAL') then 'VAL'
        when logical_or(mode = 'TRAMWAY') then 'TRAMWAY'
        else any_value(mode)
    end                                                   as mode_principal,
    logical_or(mode in ('METRO', 'RER', 'TRAIN', 'VAL'))  as est_transport_lourd,
    string_agg(distinct ligne, ', ' order by ligne)       as lignes,
    count(distinct ligne)                                 as nb_lignes,
    avg(latitude)                                         as latitude,
    avg(longitude)                                        as longitude,
    st_geogpoint(avg(longitude), avg(latitude))           as geog
from src
where latitude is not null and longitude is not null
group by nom_gare, lat_r, lon_r
