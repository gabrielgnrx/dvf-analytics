-- Couche staging : typage et nettoyage de base de la donnée brute.
-- On passe du tout-STRING à des types corrects, on normalise, et on filtre les
-- lignes inexploitables. Le nettoyage "métier" (prix au m², dédoublonnage des
-- mutations multi-lignes) se fait dans les marts.

with source as (

    select * from {{ source('raw', 'dvf_mutations') }}

),

typed as (

    select
        id_mutation,
        safe_cast(date_mutation as date)                    as date_mutation,
        nature_mutation,
        safe_cast(valeur_fonciere as float64)               as valeur_fonciere,
        nullif(adresse_numero, '')                          as adresse_numero,
        nullif(adresse_nom_voie, '')                        as adresse_nom_voie,
        nullif(code_postal, '')                             as code_postal,
        nullif(code_commune, '')                            as code_commune,
        nullif(nom_commune, '')                             as nom_commune,
        nullif(code_departement, '')                        as code_departement,
        id_parcelle,
        safe_cast(nombre_lots as int64)                     as nombre_lots,
        nullif(type_local, '')                              as type_local,
        safe_cast(surface_reelle_bati as float64)           as surface_reelle_bati,
        safe_cast(nombre_pieces_principales as int64)       as nombre_pieces,
        safe_cast(surface_terrain as float64)               as surface_terrain,
        safe_cast(longitude as float64)                     as longitude,
        safe_cast(latitude as float64)                      as latitude
    from source

),

cleaned as (

    select *
    from typed
    where date_mutation is not null
      and valeur_fonciere is not null
      and valeur_fonciere > 0
      -- on ne garde que les ventes (exclut échanges, expropriations, etc.)
      and nature_mutation = 'Vente'

)

select * from cleaned
