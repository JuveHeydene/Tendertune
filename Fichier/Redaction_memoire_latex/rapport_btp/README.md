# Mémoire BTP RAG — `rapport_btp`

Setup LaTeX complet pour le mémoire **Conception et implémentation d'une application intelligente pour l'automatisation du traitement et de la réponse aux dossiers d'appels d'offres dans le secteur du BTP** (cas SITINFRA Cameroun).

Palette **bleu `#3B5D9C`**. Ornements gravés (pgfornament), distincts du mémoire de référence. Détail dans `DECORATIONS.md`.

## Compilation

```bash
./compile.sh
# équivalent : latexmk -pdf main.tex
```

Prérequis : TeX Live avec `babel-french`, `tikz`, `pgfornament`, `tcolorbox`, `fancyhdr`, `booktabs`, `listings`, `eso-pic`, `lettrine`.

## Structure

| Fichier / dossier | Rôle |
|-------------------|------|
| `main.tex` | Assemblage du document |
| `preamble.tex` | Paquets, titres, encadrés, styles TikZ |
| `cover.tex` | Métadonnées, page de garde, page de titre intérieure |
| `decorations.tex` | Palette bleu clair et ornements |
| `sections/` | Liminaires, chapitres 1--3, conclusion, biblio, annexes |
| `figures/` | Schémas TikZ partagés |
| `images/page_garde/` | Logos ENSPY, Polytech, Keyce, IU GEE, SITINFRA |
| `images/liminaire/` | Illustrations des pages liminaires |
| `images/chapitre1/` … `chapitre3/` | Bannières et captures par chapitre |

## Chapitres

1. **État de l'art** --- contexte AO, GED, TAL, recherche d'information (BM25, RRF), RAG, bases vectorielles, documents structurés, entités et graphes, workflows / HITL, solutions.
2. **Méthodologie** --- problématique, besoins, modèle de données, architecture à deux horloges, recherche et génération, workflow, évaluation, phasage.
3. **Résultats et architecture technique** --- plateforme, composants (Qdrant, BGE-M3, LangGraph, \ldots), performances, comparaisons, discussion.

Les outils nommés (Docling, Qdrant, LlamaIndex, \ldots) apparaissent au chapitre 3, pas dans l'état de l'art.

## Personnalisation

1. **Page de garde** : bloc « MÉTADONNÉES » de `cover.tex` (titre, auteur, jury, année).
2. **Bannière de chapitre** : déposer `chapitreN-banner.png` dans `images/chapitreN/`, puis juste avant `\chapter{...}` :
   ```latex
   \setchapterimage{chapitre1-banner.png}
   ```
3. **Contenu** : éditer les fichiers de `sections/`.

## Encadrés

| Commande | Usage |
|----------|--------|
| `btpbox` | Point clé / synthèse |
| `btpdef` | Définition |
| `btpnote` | À retenir |
| `btpwarn` | Point de vigilance |
| `btpquote` | Problématique, citation mise en avant |

## Palette

| Couleur | Rôle |
|---------|------|
| `btpblue` | Bleu principal `#3B5D9C` |
| `btpsky` | Accent ciel |
| `btplight` | Filets, fonds légers |
| `btppale` | Fond des encadrés et tableaux |
| `btpdeep` | Titres |
| `btpink` | Encre du corps |
