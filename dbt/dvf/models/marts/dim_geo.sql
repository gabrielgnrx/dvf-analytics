-- Dimension géographique au grain commune (arrondissement pour Paris).
-- Le centroïde est calculé à partir des transactions géolocalisées.

with communes as (

    select
        code_commune,
        approx_top_count(nom_commune, 1)[offset(0)].value as nom_commune,
        any_value(code_departement)                       as code_departement,
        approx_top_count(code_postal, 1)[offset(0)].value as code_postal_principal,
        avg(latitude)                                     as latitude,
        avg(longitude)                                    as longitude
    from {{ ref('int_dvf__mutations') }}
    where code_commune is not null
    group by code_commune

)

select
    c.code_commune                       as geo_key,
    c.code_commune,
    c.nom_commune,
    c.code_postal_principal,
    c.code_departement,
    d.nom_departement,
    d.zone,
    c.latitude,
    c.longitude,
    st_geogpoint(c.longitude, c.latitude) as centroide
from communes c
left join {{ ref('ref_departements') }} d using (code_departement)
