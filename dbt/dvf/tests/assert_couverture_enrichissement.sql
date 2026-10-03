-- Contrôle de couverture des sources d'enrichissement, pondéré par les ventes :
-- au moins 95 % des ventes doivent avoir un revenu communal, un taux de DPE et
-- une distance aux gares. En dessous, une jointure a probablement cassé
-- (changement de code commune, format de source modifié).
-- Le test échoue s'il renvoie une ligne.

with couverture as (

    select
        avg(if(g.revenu_median_uc is not null, 1, 0)) as part_revenu,
        avg(if(g.part_dpe_fg_pct is not null, 1, 0))  as part_dpe,
        avg(if(f.dist_gare_m is not null, 1, 0))      as part_transports
    from {{ ref('fact_transactions') }} f
    join {{ ref('dim_geo') }} g using (geo_key)
    where f.est_vente_simple

)

select *
from couverture
where part_revenu < 0.95 or part_dpe < 0.95 or part_transports < 0.95
