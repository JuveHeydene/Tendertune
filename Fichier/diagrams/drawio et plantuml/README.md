# Diagrammes du mémoire — sources PlantUML

Cinq diagrammes pour la section **méthodologie**, écrits en **PlantUML** (notation UML), avec la même charte de couleurs pastel que les diagrammes de séquence du dossier parent.

## Les cinq diagrammes

| Fichier source | Diagramme | Vocabulaire | Format de page conseillé |
|---|---|---|---|
| `composants.puml` | Diagramme de composants (composants, **ports**, interfaces fournies/requises) | générique | **paysage** |
| `multi_agents.puml` | Organisation multi-agent de l'horloge B | générique | portrait, pleine largeur |
| `architecture_logicielle.puml` | Architecture logicielle en couches | générique | portrait, pleine largeur |
| `architecture_technique.puml` | Architecture technique (mêmes couches) | **technologies réelles** | portrait, pleine largeur |
| `deploiement.puml` | Diagramme de déploiement (nœuds, artefacts, environnement d'exécution) | technologies réelles | **paysage** |

Un seul diagramme de composants couvre les **deux horloges** : elles apparaissent comme deux paquetages parallèles qui partagent la couche d'accès aux données et les services de modèles. En paysage il reste parfaitement lisible ; inutile de le scinder en deux.

## Formats produits pour chaque diagramme

| Extension | Usage |
|---|---|
| `.puml` | **la source** — c'est le seul fichier à modifier |
| `.png` | aperçu rapide (à l'écran, dans un Markdown, un mail) |
| `.svg` | vectoriel, pour un traitement de texte ou une présentation |
| `.tex` | **export TikZ vectoriel** — c'est ce qu'on insère dans le mémoire |

Le `.tex` est produit par PlantUML lui-même : le rendu utilise les **polices LaTeX du mémoire** et reste vectoriel à l'impression (pas de pixellisation).

## Régénérer après modification d'un `.puml`

```bash
JAR=/home/juve/.vscode/extensions/jebbs.plantuml-2.18.1/plantuml.jar
cd "/home/juve/Lectures_&_projects/Projets/AI_ML/Tendertune/Nouvelle_Architecture/diagrammes_memoire"

f=composants                      # ou multi_agents, architecture_logicielle, …
java -jar $JAR -tpng  "$f.puml"                  # aperçu
java -jar $JAR -tsvg  "$f.puml"                  # vectoriel générique
java -jar $JAR "-tlatex:nopreamble" "$f.puml"    # export TikZ pour le mémoire

# puis réinstaller dans le mémoire
cp "$f.tex" ../../Fichier/Redaction_memoire_latex/rapport_btp/figures/uml_$f.tex
```

## Insertion dans le mémoire

Les exports sont déjà copiés dans `rapport_btp/figures/` sous le préfixe `uml_`.
Ils ne demandent aucun paquet supplémentaire (`tikz` est déjà chargé par le préambule).

### Diagrammes en portrait (pleine largeur)

```latex
\begin{figure}[p]
  \centering
  \resizebox{\linewidth}{!}{\input{figures/uml_multi_agents.tex}}
  \caption{Organisation multi-agent de l'horloge B : superviseur, agents
           experts et génération}
  \label{fig:multi-agents}
\end{figure}
```

Idem avec `uml_architecture_logicielle.tex` et `uml_architecture_technique.tex`.

### Diagrammes en paysage (composants et déploiement)

Ces deux-là sont larges : en portrait le texte tombe autour de 5 pt. En paysage il
passe au double et devient confortable.

```latex
\usepackage{rotating}          % à ajouter au préambule s'il n'y est pas

\begin{sidewaysfigure}
  \centering
  \resizebox{\textheight}{!}{\input{figures/uml_composants.tex}}
  \caption{Diagramme de composants de la plateforme}
  \label{fig:composants}
\end{sidewaysfigure}
```

Idem avec `uml_deploiement.tex`.

> `\resizebox{\textheight}{!}` et non `\linewidth` : sur une page tournée, c'est la
> hauteur du bloc de texte qui devient la largeur utile.

## Version draw.io de l'architecture technique

Deux mises en page du même contenu, à ouvrir directement dans draw.io / diagrams.net
(XML non compressé, géométrie explicite — donc aucune recomposition automatique
au chargement) :

| Fichier | Format | Page | Quand l'utiliser |
|---|---|---|---|
| `architecture_technique_long.drawio` | **portrait** | 780 × 1150 | insertion dans le mémoire en pleine largeur |
| `architecture_technique_large.drawio` | **paysage** | 1500 × 820 | soutenance, poster, page tournée |

Aperçus dans `apercus/architecture_technique_long.png` et `..._large.png`.

Principes de tracé retenus pour éviter l'enchevêtrement de flèches :

- les couches sont des bandes horizontales, les liaisons ne relient que des bandes
  voisines ;
- les deux horloges sont deux groupes côte à côte, chacun avec son propre fil
  vertical, sans liaison de l'un vers l'autre ;
- tous les accès aux entrepôts passent par une **couche d'accès aux données**
  unique : une seule flèche descend vers les entrepôts au lieu d'un faisceau ;
- les appels au service de modèles empruntent un **couloir dédié** (trait
  discontinu, couleur distincte), à l'écart du flux principal ;
- là où un croisement est inévitable, la liaison porte un **saut d'arc**
  (`jumpStyle=arc`) pour lever l'ambiguïté.

Les scripts qui ont produit ces fichiers sont versionnés à côté
(`gen_drawio.py`, `build_long.py`, `build_large.py`) : modifier les coordonnées
puis relancer `python3 build_long.py` régénère le `.drawio` **et** son aperçu PNG.

## Charte graphique

Reprise des diagrammes de séquence existants : fond blanc, police *Latin Modern
Roman* (celle du mémoire), pas d'ombres, flèches gris foncé, et une couleur pastel
par rôle — bleu pour la présentation et la passerelle, vert pour l'ingestion, mauve pour
l'orchestration conversationnelle, orange pour les outils et livrables, rose pour les
services de modèles, et des teintes distinctes par entrepôt de données.

## Note sur les figures TikZ manuelles

Le même dossier contient aussi une première série écrite directement en TikZ
(`fig_composants.tex`, `fig_multi_agents.tex`, `fig_architecture_logicielle.tex`,
`fig_architecture_technique.tex`, `fig_deploiement.tex`, aperçus dans `apercus/`).
Elles sont conservées, mais **ce ne sont pas des diagrammes UML** : ce sont des
schémas de synthèse en boîtes et flèches, sans ports ni interfaces. Les fichiers
`uml_*` décrits ci-dessus sont ceux qui respectent la notation UML.
