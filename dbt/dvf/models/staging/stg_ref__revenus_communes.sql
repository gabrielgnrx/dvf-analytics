-- Revenu disponible par unité de consommation (INSEE Filosofi), par commune
-- et par arrondissement pour Paris. Les valeurs sous secret statistique
-- (petites communes) arrivent vides et restent nulles.

select
    trim(code_commune)                                    as code_commune,
    trim(libelle_commune)                                 as libelle_commune,
    safe_cast(nb_menages as int64)                        as nb_menages_fiscaux,
    safe_cast(revenu_median as float64)                   as revenu_median_uc,
    safe_cast(revenu_d1 as float64)                       as revenu_d1_uc,
    safe_cast(revenu_d9 as float64)                       as revenu_d9_uc,
    safe_cast(part_pensions_pct as float64)               as part_pensions_pct,
    safe_cast(millesime as int64)                         as millesime_revenus
from {{ source('raw', 'ref_revenus_communes') }}
where code_commune is not null
