-- Table de faits : une ligne par mutation (vente), reliée aux dimensions
-- temps, géographie et bien. Le prix au m² n'est renseigné que lorsqu'il a un
-- sens (vente simple d'un logement) et un indicateur signale les valeurs
-- aberrantes plutôt que de les supprimer : la décision d'exclure reste visible
-- et auditable dans le BI.

with m as (

    select * from {{ ref('int_dvf__mutations') }}

),

enrichi as (

    select
        m.*,
        {{ classe_pieces('nb_pieces', 'type_bien') }}   as classe_pieces,
        {{ tranche_surface('surface_habitable') }}     as tranche_surface,
        if(est_vente_simple, round(valeur_fonciere / surface_habitable, 2), null) as prix_m2
    from m

)

select
    id_mutation                                             as transaction_id,
    cast(format_date('%Y%m%d', date_mutation) as int64)     as date_key,
    code_commune                                            as geo_key,
    {{ dbt_utils.generate_surrogate_key(['type_bien', 'classe_pieces', 'tranche_surface']) }} as bien_key,

    date_mutation,
    code_departement,
    type_bien,
    valeur_fonciere,
    surface_habitable,
    surface_terrain,
    nb_pieces,
    nb_appartements,
    nb_maisons,
    nb_dependances,
    nb_locaux_activite,
    nb_parcelles,
    nombre_lots,
    prix_m2,
    est_vente_simple,
    -- Bornes calibrées sur l'Île-de-France (cf. rapport de profilage) :
    -- en dessous de 1 000 €/m² ou au-dessus de 30 000 €/m², il s'agit
    -- quasi toujours de ventes atypiques (droits partiels, erreurs de saisie,
    -- ventes en bloc mal ventilées).
    (prix_m2 is not null and prix_m2 between 1000 and 30000) as est_prix_m2_fiable,
    latitude,
    longitude,
    nb_lignes_source
from enrichi
