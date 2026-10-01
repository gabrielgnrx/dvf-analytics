-- Dimension "bien" : typologie x taille. Grain : combinaison type / pièces /
-- tranche de surface. Sert aux analyses par segment (T2 parisiens, maisons
-- de grande couronne, etc.).

with combos as (

    select distinct
        type_bien,
        {{ classe_pieces('nb_pieces', 'type_bien') }}       as classe_pieces,
        {{ tranche_surface('surface_habitable') }}         as tranche_surface
    from {{ ref('int_dvf__mutations') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['type_bien', 'classe_pieces', 'tranche_surface']) }} as bien_key,
    type_bien,
    classe_pieces,
    tranche_surface,
    type_bien in ('Appartement', 'Maison') as est_logement
from combos
