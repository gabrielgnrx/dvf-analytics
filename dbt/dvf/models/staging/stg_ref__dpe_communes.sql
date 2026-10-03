-- Parc de logements diagnostiqués par commune : nombre de DPE et part des
-- "passoires thermiques" (étiquettes F et G), interdites progressivement à la
-- location depuis 2025 (G) et 2028 (F).

with src as (

    select
        trim(code_commune)                                as code_commune,
        upper(trim(etiquette_dpe))                        as etiquette,
        cast(nb_dpe as int64)                             as nb_dpe
    from {{ source('raw', 'ref_dpe_communes') }}
    where upper(trim(etiquette_dpe)) in ('A', 'B', 'C', 'D', 'E', 'F', 'G')

)

select
    code_commune,
    sum(nb_dpe)                                           as nb_dpe,
    sum(if(etiquette in ('A', 'B'), nb_dpe, 0))           as nb_dpe_ab,
    sum(if(etiquette in ('F', 'G'), nb_dpe, 0))           as nb_dpe_fg,
    round(safe_divide(sum(if(etiquette in ('F', 'G'), nb_dpe, 0)), sum(nb_dpe)) * 100, 1) as part_dpe_fg_pct,
    round(safe_divide(sum(if(etiquette in ('A', 'B'), nb_dpe, 0)), sum(nb_dpe)) * 100, 1) as part_dpe_ab_pct
from src
group by code_commune
