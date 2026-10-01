-- Ventes comparées au prix "attendu" par le modèle : sert la page analytique
-- du dashboard (biens vendus nettement au-dessus ou en dessous du marché local,
-- dispersion du marché par commune).

select
    f.transaction_id,
    f.date_key,
    f.geo_key,
    f.bien_key,
    f.date_mutation,
    f.type_bien,
    f.surface_habitable,
    f.valeur_fonciere,
    f.prix_m2,
    p.prix_m2_predit,
    p.ecart_pct,
    case
        when p.ecart_pct <= -20 then 'Sous le marché (< -20 %)'
        when p.ecart_pct < -10 then 'Légèrement sous (-20 à -10 %)'
        when p.ecart_pct <= 10 then 'Au prix du marché (±10 %)'
        when p.ecart_pct < 20 then 'Légèrement au-dessus (10 à 20 %)'
        else 'Au-dessus du marché (> 20 %)'
    end as positionnement_prix
from {{ ref('fact_transactions') }} f
join {{ source('ml', 'predictions_prix_m2') }} p using (transaction_id)
