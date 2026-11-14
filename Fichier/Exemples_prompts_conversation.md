# Exemples de prompts — Conversations

Ce fichier donne des formulations qui fonctionnent bien avec le routeur actuel
(`app/workflow/nodes/superviseur.py` + repli mots-clés `app/workflow/nodes/route.py`).
Le routeur classe chaque message en une intention (question/recherche, rédaction
de section, export, discussion) — plus la formulation est explicite, plus la
classification est fiable. Un petit modèle local (granite3.3:2b) fait cette
classification : les prompts courts et concrets ci-dessous limitent le risque
de mauvaise classification.

## 1. Poser une question (recherche patrimoine / DAO)

Fonctionne bien quand la question est complète et autonome (pas de "et pour
ça ?" sans contexte) :

- « Quelles sont nos références de chantiers de terrassement de plus de
  50 000 m³ réalisés dans les 5 dernières années ? »
- « Quel est le délai d'exécution prévu par le CCAP de ce dossier ? »
- « Avons-nous déjà une attestation d'assurance décennale en cours de
  validité dans le patrimoine ? »

Une question composée de plusieurs recherches indépendantes est automatiquement
découpée (ex. « Quels sont nos effectifs de conducteurs de travaux ET nos
certifications ISO 14001 ? ») — chaque partie est cherchée séparément puis
agrégée dans la réponse.

## 2. Rédiger / régénérer une section du mémoire

Le routeur reconnaît un mot d'action (« génère », « rédige », « écris la
section ») associé à un mot-clé de thème. Formulations qui déclenchent
correctement chaque section du plan par défaut :

| Section | Mots-clés qui la déclenchent | Exemple de prompt |
|---|---|---|
| Présentation de l'entreprise | présentation, entreprise, société | « Rédige la présentation de l'entreprise en mettant en avant notre expérience en VRD. » |
| Moyens humains | moyens, personnel, équipe, effectif | « Génère la section sur nos moyens humains pour ce chantier. » |
| Références et projets similaires | référence, chantier similaire, projet similaire | « Rédige nos références sur des projets similaires de voirie urbaine. » |
| Méthodologie et organisation | méthode, organisation, phasage | « Génère la méthodologie et l'organisation de chantier prévue. » |
| Planning et délais | planning, délai, calendrier | « Rédige le planning et les délais d'exécution. » |

Pour tout le mémoire d'un coup : « Génère tout le mémoire » ou « Rédige le
dossier complet » (traite les 5 sections du plan par défaut à la suite).

**Conseil** : si le dossier a un plan extrait automatiquement du RC (onglet
Plan), les titres réels de ce plan priment — reprenez le titre exact affiché
dans l'onglet Plan pour cibler la bonne section plutôt que les mots-clés
génériques ci-dessus.

**Pour affiner une section déjà générée** : ajoutez une consigne précise dans
votre demande plutôt qu'un mot vague — « Régénère la méthodologie en insistant
sur la gestion des réseaux enterrés » donne un bien meilleur résultat que
« refais la méthodologie ». Cette consigne est transmise telle quelle au
prompt de rédaction (`custom_instruction`).

**Pour enrichir une section sans repartir de zéro** : un mot comme « ajoute »,
« complète », « en plus » ou « enrichis » (voir `EXTEND_KEYWORDS`) fait que le
texte déjà rédigé est fourni au modèle comme base à compléter, pas comme
brouillon à jeter — « Ajoute un paragraphe sur nos certifications qualité à
cette section » construit sur l'existant plutôt que de le remplacer.

## 3. Demander une proposition (même sans source patrimoine)

Par défaut, la rédaction est strictement sourcée : sans extrait patrimoine
pertinent, le modèle note l'absence dans « abstentions » plutôt que
d'inventer. Mais tout ne peut pas être dans le patrimoine — un mot comme
« propose », « suggère » ou « imagine » (voir `PROPOSAL_KEYWORDS`) autorise le
modèle à structurer un texte plausible (cadrage, méthodologie générale) même
sans source précise :

- « Fais-moi une proposition sur la présentation du projet ou de
  l'entreprise. »
- « Suggère une organisation de chantier pour ce type de projet. »

Le texte produit porte alors toujours un bandeau **« ⚠️ Proposition non
sourcée sur le patrimoine — à valider avant tout dépôt »** en tête (posé par
le code, visible dans le chat, l'onglet Sections et tout export). Le modèle
reste interdit d'inventer un FAIT VÉRIFIABLE précis sur l'entreprise (chiffre,
certification, date, projet réel) — ces éléments ressortent en
« [À COMPLÉTER : ...] » plutôt que d'être inventés.

## 4. Exporter le mémoire

Un mot explicite et sans ambiguïté est nécessaire — un message vague comme
« pourquoi ? » ou « et donc ? » ne doit JAMAIS déclencher un téléchargement
(corrigé — voir le garde-fou dans `run_superviseur`). Formulations fiables :

- « Exporte le mémoire en PDF. »
- « Télécharge le dossier en Word. »
- « Exporte en markdown. »

## 5. Joindre un document depuis la conversation

Cliquer sur 📎 propose un choix explicite avant tout envoi :
- **Aide ponctuelle pour ce dossier** (annexe) — sert uniquement à répondre
  dans cette conversation, jamais réutilisé ailleurs ni indexé dans le
  patrimoine général.
- **Ajouter au patrimoine** — réutilisable sur tous les futurs dossiers
  (réservé aux documents de référence validés : méthodologies types, CV,
  certifications).

## 6. Limites connues

- Un message très court et ambigu (un seul mot interrogatif) reste plus
  fragile à classifier qu'une phrase complète — préférez toujours une
  formulation explicite sur ce que vous attendez (question, rédaction,
  export, proposition).
- L'onglet Exigences permet de relier une exigence à une section (bouton
  « Classer les exigences par section », onglet Sections) — cette
  association est injectée dans le prompt de rédaction pour que la section
  traite vraiment les exigences qui la concernent, mais rien ne garantit que
  la classification automatique soit parfaite : vérifiez/confirmez les
  propositions de l'IA dans l'onglet Sections avant de générer.
