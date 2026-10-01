# Modèle prix au m² — résultats (run du 1er octobre 2026)

Ventes exploitables (vente simple d'un logement, prix au m² fiable) : 675 769.
Découpage temporel : entraînement 2021-2023 (442 186), validation 2024
(107 086), test 2025 (126 497).

## Performance

| Jeu | Modèle | MAE (€/m²) | MdAPE | Part à ±10 % | R² (log) |
|---|---|---:|---:|---:|---:|
| Validation 2024 | LightGBM | 1 037 | 13,1 % | 39,4 % | 0,788 |
| Validation 2024 | Baseline médiane commune x type | 1 245 | 16,8 % | 32,3 % | 0,699 |
| Test 2025 | LightGBM | 1 025 | 13,0 % | 39,6 % | 0,801 |
| Test 2025 | Baseline médiane commune x type | 1 208 | 16,3 % | 32,9 % | 0,718 |

Sur l'année 2025, jamais vue à l'entraînement, le modèle réduit l'erreur
médiane de 16,3 % à 13,0 % par rapport à la règle métier simple.

## Erreur par segment (test 2025)

| Département | n | Prix m² médian | MdAPE |
|---|---:|---:|---:|
| 75 | 28 752 | 9 737 | 13,8 % |
| 93 | 11 942 | 3 942 | 13,7 % |
| 92 | 18 090 | 6 525 | 13,4 % |
| 94 | 13 238 | 4 763 | 13,0 % |
| 78 | 14 896 | 3 846 | 12,9 % |
| 95 | 11 276 | 3 367 | 12,3 % |
| 91 | 13 012 | 3 155 | 12,2 % |
| 77 | 15 291 | 3 061 | 12,0 % |

| Type | n | Prix m² médian | MdAPE |
|---|---:|---:|---:|
| Maison | 37 787 | 3 536 | 13,2 % |
| Appartement | 88 710 | 5 694 | 13,0 % |

## Importance des variables (gain)

Commune 58,9 %, département 23,7 %, surface habitable 3,7 %, coordonnées
(lat/lon logement et centroïde commune) environ 9 %, surface terrain 1,8 %,
type de bien 1,3 %, pièces 0,6 %, tendance temporelle 0,4 %.

## Lecture

- La localisation explique l'essentiel du prix. DVF ne contient ni l'étage,
  ni l'état du bien, ni le DPE : c'est le plafond de précision structurel du
  jeu de données, autour de 13 % d'erreur médiane.
- L'erreur est la plus forte à Paris et en Seine-Saint-Denis, deux marchés
  très hétérogènes à l'intérieur d'une même commune ou d'un même arrondissement.
- Pistes d'amélioration : variables de voisinage (prix médian glissant à
  500 m, IRIS), distance aux gares, données DPE de l'ADEME.
