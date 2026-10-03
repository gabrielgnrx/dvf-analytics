-- Dimension géographique au grain commune (arrondissement pour Paris).
-- Le centroïde est calculé à partir des transactions géolocalisées.
-- Enrichie avec les revenus (INSEE) et la performance énergétique (ADEME).

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
    st_geogpoint(c.longitude, c.latitude) as centroide,
    -- Contexte socio-économique (INSEE Filosofi)
    r.revenu_median_uc,
    r.revenu_d1_uc,
    r.revenu_d9_uc,
    round(safe_divide(r.revenu_d9_uc, r.revenu_d1_uc), 2) as rapport_d9_d1,
    r.nb_menages_fiscaux,
    r.millesime_revenus,
    -- Performance énergétique du parc (ADEME)
    e.nb_dpe,
    e.part_dpe_fg_pct,
    e.part_dpe_ab_pct
from communes c
left join {{ ref('ref_departements') }} d using (code_departement)
left join {{ ref('stg_ref__revenus_communes') }} r using (code_commune)
left join {{ ref('stg_ref__dpe_communes') }} e using (code_commune)
