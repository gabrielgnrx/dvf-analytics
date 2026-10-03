-- Accessibilité en transports de chaque vente géolocalisée :
--   - distance à la gare de transport lourd (métro, RER, train, VAL) la plus proche ;
--   - nombre de gares lourdes distinctes à moins de 1 km ;
--   - distance à la future gare du Grand Paris Express la plus proche.
--
-- Optimisations : les calculs se font sur les points distincts (arrondis à
-- ~10 m, de nombreuses ventes partagent un immeuble), et la jointure spatiale
-- est bornée par ST_DWITHIN pour ne pas comparer chaque vente à chaque gare.
-- Au-delà de la borne, la distance est plafonnée (valeur "au moins X m").
--
-- Limite connue : la liste des gares est celle d'aujourd'hui. Une vente de
-- 2021 près d'une gare ouverte en 2024 (prolongement de la ligne 14, par
-- exemple) est comptée comme desservie.

{{ config(materialized='table') }}

{% set borne_gare = 5000 %}
{% set borne_gpe = 10000 %}

with ventes as (

    select
        id_mutation,
        round(latitude, 4)  as lat_r,
        round(longitude, 4) as lon_r
    from {{ ref('int_dvf__mutations') }}
    where latitude is not null and longitude is not null

),

points as (

    select lat_r, lon_r, st_geogpoint(lon_r, lat_r) as geog
    from (select distinct lat_r, lon_r from ventes)

),

gares as (

    select nom_gare, mode_principal, geog
    from {{ ref('stg_ref__gares') }}
    where est_transport_lourd

),

gpe as (

    select nom_gare, geog
    from {{ ref('stg_ref__gares_projet') }}
    where est_grand_paris_express

),

proche_gare as (

    select
        p.lat_r,
        p.lon_r,
        array_agg(
            struct(st_distance(p.geog, g.geog) as distance_m, g.nom_gare, g.mode_principal)
            order by st_distance(p.geog, g.geog)
            limit 1
        )[offset(0)] as top,
        count(distinct if(st_distance(p.geog, g.geog) <= 1000, g.nom_gare, null)) as nb_gares_1km
    from points p
    join gares g on st_dwithin(p.geog, g.geog, {{ borne_gare }})
    group by p.lat_r, p.lon_r

),

proche_gpe as (

    select
        p.lat_r,
        p.lon_r,
        array_agg(
            struct(st_distance(p.geog, g.geog) as distance_m, g.nom_gare)
            order by st_distance(p.geog, g.geog)
            limit 1
        )[offset(0)] as top
    from points p
    join gpe g on st_dwithin(p.geog, g.geog, {{ borne_gpe }})
    group by p.lat_r, p.lon_r

)

select
    v.id_mutation,
    round(coalesce(pg.top.distance_m, {{ borne_gare }}), 0)  as dist_gare_m,
    pg.top.nom_gare                                          as gare_proche,
    pg.top.mode_principal                                    as mode_gare_proche,
    coalesce(pg.nb_gares_1km, 0)                             as nb_gares_1km,
    round(coalesce(gp.top.distance_m, {{ borne_gpe }}), 0)   as dist_gpe_m,
    gp.top.nom_gare                                          as gare_gpe_proche
from ventes v
left join proche_gare pg using (lat_r, lon_r)
left join proche_gpe gp using (lat_r, lon_r)
