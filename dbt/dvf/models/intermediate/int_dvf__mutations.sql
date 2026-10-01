-- Couche intermediate : passage du grain "ligne de fichier" au grain "mutation".
--
-- Le piège central de DVF : une mutation (id_mutation) est éclatée sur
-- plusieurs lignes (une par local, par parcelle, par nature de culture), et la
-- valeur foncière est RÉPÉTÉE sur chaque ligne. Sommer valeur_fonciere ou
-- diviser par la surface d'une seule ligne donne des prix au m² faux.
--
-- Ici on :
--   1. supprime les doublons stricts de lignes ;
--   2. dédoublonne les locaux (un local apparaît une fois par nature de culture) ;
--   3. agrège à la mutation : valeur unique, surface habitable totale,
--      nombre de logements, de dépendances et de locaux d'activité ;
--   4. qualifie la mutation (vente simple d'un seul logement ou non) pour
--      savoir si un prix au m² a un sens.

with lignes as (

    select distinct
        id_mutation,
        date_mutation,
        valeur_fonciere,
        code_postal,
        code_commune,
        nom_commune,
        code_departement,
        id_parcelle,
        nombre_lots,
        type_local,
        surface_reelle_bati,
        nombre_pieces,
        surface_terrain,
        longitude,
        latitude
    from {{ ref('stg_dvf__mutations') }}

),

-- Un local = (parcelle, type, surface, pièces). Les lignes répétées par nature
-- de culture partagent ces attributs : on ne les compte qu'une fois.
locaux as (

    select distinct
        id_mutation,
        id_parcelle,
        type_local,
        surface_reelle_bati,
        nombre_pieces
    from lignes
    where type_local is not null

),

locaux_agg as (

    select
        id_mutation,
        countif(type_local = 'Appartement')                         as nb_appartements,
        countif(type_local = 'Maison')                              as nb_maisons,
        countif(type_local = 'Dépendance')                          as nb_dependances,
        countif(type_local like 'Local industriel%')                as nb_locaux_activite,
        sum(case when type_local in ('Appartement', 'Maison')
                 then surface_reelle_bati end)                      as surface_habitable,
        sum(case when type_local in ('Appartement', 'Maison')
                 then nombre_pieces end)                            as nb_pieces
    from locaux
    group by id_mutation

),

-- Surface de terrain : une valeur par (parcelle, nature de culture). On prend
-- le max par parcelle puis la somme sur les parcelles, approximation prudente.
terrain as (

    select id_mutation, sum(surface_terrain_parcelle) as surface_terrain
    from (
        select id_mutation, id_parcelle, max(surface_terrain) as surface_terrain_parcelle
        from lignes
        group by id_mutation, id_parcelle
    )
    group by id_mutation

),

mutation as (

    select
        id_mutation,
        any_value(date_mutation)                    as date_mutation,
        -- valeur répétée sur chaque ligne : max = la valeur de la mutation
        max(valeur_fonciere)                        as valeur_fonciere,
        count(distinct valeur_fonciere)             as nb_valeurs_distinctes,
        any_value(code_departement)                 as code_departement,
        -- commune et code postal majoritaires si la mutation en couvre plusieurs
        approx_top_count(code_commune, 1)[offset(0)].value  as code_commune,
        approx_top_count(nom_commune, 1)[offset(0)].value   as nom_commune,
        approx_top_count(code_postal, 1)[offset(0)].value   as code_postal,
        count(distinct id_parcelle)                 as nb_parcelles,
        max(nombre_lots)                            as nombre_lots,
        avg(longitude)                              as longitude,
        avg(latitude)                               as latitude,
        count(*)                                    as nb_lignes_source
    from lignes
    group by id_mutation

)

select
    m.id_mutation,
    m.date_mutation,
    m.valeur_fonciere,
    m.code_departement,
    m.code_commune,
    m.nom_commune,
    m.code_postal,
    m.nb_parcelles,
    m.nombre_lots,
    m.longitude,
    m.latitude,
    m.nb_lignes_source,
    m.nb_valeurs_distinctes,
    coalesce(l.nb_appartements, 0)      as nb_appartements,
    coalesce(l.nb_maisons, 0)           as nb_maisons,
    coalesce(l.nb_dependances, 0)       as nb_dependances,
    coalesce(l.nb_locaux_activite, 0)   as nb_locaux_activite,
    l.surface_habitable,
    l.nb_pieces,
    t.surface_terrain,

    case
        when coalesce(l.nb_appartements, 0) = 1 and coalesce(l.nb_maisons, 0) = 0 then 'Appartement'
        when coalesce(l.nb_maisons, 0) = 1 and coalesce(l.nb_appartements, 0) = 0 then 'Maison'
        when coalesce(l.nb_appartements, 0) + coalesce(l.nb_maisons, 0) > 1 then 'Multi-logements'
        when coalesce(l.nb_locaux_activite, 0) > 0 then 'Local commercial'
        when coalesce(l.nb_dependances, 0) > 0 then 'Dépendance seule'
        else 'Terrain / non bâti'
    end as type_bien,

    -- Vente "simple" : un seul logement (dépendances tolérées, ex. cave,
    -- parking), aucun local d'activité, une seule valeur foncière. C'est le
    -- seul périmètre où le prix au m² est interprétable.
    (
        coalesce(l.nb_appartements, 0) + coalesce(l.nb_maisons, 0) = 1
        and coalesce(l.nb_locaux_activite, 0) = 0
        and m.nb_valeurs_distinctes = 1
        and l.surface_habitable >= 9
    ) as est_vente_simple

from mutation m
left join locaux_agg l using (id_mutation)
left join terrain t using (id_mutation)
