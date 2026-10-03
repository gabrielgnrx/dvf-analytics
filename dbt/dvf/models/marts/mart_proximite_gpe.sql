-- Effet "Grand Paris Express" : évolution du prix au m² selon la distance à
-- la future gare la plus proche, hors Paris (les gares du projet sont en
-- petite et grande couronne ; garder Paris fausserait la tranche éloignée).
--
-- Lecture : si les biens proches d'une future gare se valorisent plus vite
-- que les biens éloignés de la même zone, l'écart d'évolution est un indice
-- d'anticipation du marché. Corrélation, pas causalité : d'autres facteurs
-- (rénovation urbaine, typologie des quartiers) jouent aussi.

with ventes as (

    select
        extract(year from f.date_mutation) as annee,
        g.zone,
        f.type_bien,
        f.tranche_dist_gpe,
        f.prix_m2
    from {{ ref('fact_transactions') }} f
    join {{ ref('dim_geo') }} g using (geo_key)
    where f.est_prix_m2_fiable
      and f.code_departement != '75'
      and f.type_bien in ('Appartement', 'Maison')
      and f.tranche_dist_gpe is not null

),

agg as (

    select
        annee,
        zone,
        type_bien,
        tranche_dist_gpe,
        count(*)                                                  as nb_ventes,
        approx_quantiles(prix_m2, 100)[offset(50)]                as prix_m2_median
    from ventes
    group by annee, zone, type_bien, tranche_dist_gpe

)

select
    *,
    round(
        (prix_m2_median / first_value(prix_m2_median) over (
            partition by zone, type_bien, tranche_dist_gpe order by annee
        ) - 1) * 100, 1
    ) as evolution_depuis_debut_pct
from agg
