# Motifs décoratifs (`decorations.tex`)

Ornements gravés « vectorian » via `pgfornament`, déclinés en **bleu clair**.
Inspirés des mémoires à cadre ornemental, sans en copier le vocabulaire
graphique : double filet, coins fleuronnés, filets à volute pour les
chapitres, petits motifs en pied de page.

## Commandes publiques

| Commande | Usage |
|----------|--------|
| `\btpCoverFrame` | Cadre ornemental de la page de garde |
| `\btpLightFrame` | Cadre allégé (titre intérieur, dédicace) |
| `\btpRule[largeur]{couleur}` | Séparateur centré à fleuron |
| `\btpSectionRule` | Filet sous les titres de section |
| `\btpEndMark` | Fleuron de fin de partie |
| `\btpLiminaryRule` | Volute des pages liminaires |
| `\btpIntro{L}{ettre initiale...}` | Accroche de chapitre en lettrine |
| `\btpChapterBanner{fichier}` | Bandeau image sous le titre de chapitre |
| `\setchapterimage{fichier}` | Alias de `\btpChapterBanner` |

## Palette

Définie en tête de `decorations.tex` :

- `btpblue` — bleu principal (`#3B5D9C`)
- `btpsky` — `btpblue!58!white` (filets intérieurs, volutes)
- `btplight` — `btpblue!30!white` (filets, pieds de page)
- `btppale` — `btpblue!10!white` (fonds d'encadrés)
- `btpdeep` — `btpblue!58!black` (titres)
- `maindeco` — alias de `btpblue`

Toute la famille se recalcule en changeant uniquement `btpblue`.

## Numéros d'ornements

Redéfinissables d'un bloc en tête de `decorations.tex` :

`\btpOrnCorner`, `\btpOrnCornerLight`, `\btpOrnBand`, `\btpOrnRule`,
`\btpOrnFlourish`, `\btpOrnSmall`, `\btpOrnLeaf`.
