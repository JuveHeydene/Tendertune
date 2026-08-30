# Base de données et interface utilisateur — ce qui change en V2

> **Statut** : document de conception, suite directe de `architecture_agentique_retrieval_generation.md` (toutes les décisions de son §7 sont validées). Ce document répond à deux questions : faut-il modifier le schéma SQL ? Comment exposer `exigences`, `outline_items`, `reviews` et `dossiers` sur l'interface, qui est aujourd'hui très pauvre ?
> **Méthode** : diagnostic de l'existant d'abord (code lu, pas supposé), puis proposition.

---

## 1. Base de données : faut-il supprimer, ajouter, migrer ?

### 1.1 Rien à supprimer

Chaque table du schéma actuel (`champsdeBase_et_contraites_workflow.md` §2, `JOURNAL.md`) reste nécessaire — l'architecture V2 change **comment** on remplit ces tables (via des experts + boucle CRAG au lieu d'un retrieve unique), pas **ce qu'on** y stocke :

| Table | Toujours nécessaire parce que |
|---|---|
| `documents`, `chunks` | Source du retrieval, inchangée dans son rôle |
| `dossiers`, `exigences`, `outline_items` | Objets métier du workflow, aucun changement de sens |
| `generations`, `reviews` | HITL, versions — le cœur de ce que V2 doit enfin exposer en UI (§3) |
| `conversations`, `messages` | Mémoire de session (§2 du doc précédent) |
| `exports`, `tenants`, `users`, `sessions`, `refresh_tokens`, `audit_logs` | Inchangés |

**Aucune table à supprimer.**

### 1.2 Colonnes à ajouter (migrations légères, non destructives)

Deux ajouts, directement issus des décisions déjà validées :

```sql
-- Décision §7-#8 (architecture_agentique_...) : classification dynamique
-- du type de section, utilisée pour scoper chaque expert (soft filter).
-- Colonne dédiée (pas juste `extra` JSONB) car filtrée dans CHAQUE requête
-- de retrieval expert — mérite un vrai index, pas un lookup JSONB.
ALTER TABLE chunks
    ADD COLUMN section_type VARCHAR(16)
        CHECK (section_type IN ('rc','ccap','cctp','dpgf','bpu','memoire','reference','autre')
               OR section_type IS NULL);

CREATE INDEX idx_chunks_section_type ON chunks(section_type);

-- La confiance et la méthode de classification (heuristique|llm) restent
-- dans `chunks.extra` (JSONB déjà existant) : ce sont des infos d'audit,
-- jamais utilisées dans une clause WHERE de retrieval — pas besoin d'un
-- index dédié.
-- extra.section_type_confidence : float
-- extra.section_type_method     : "heuristic" | "llm"


-- Décision §7-#7 : résumé de progression de dossier, précalculé à
-- l'approve (pas recalculé à chaque question).
ALTER TABLE generations
    ADD COLUMN summary_short TEXT;
```

Rien d'autre ne nécessite une colonne : `messages.meta` (JSONB), `generations.context_snapshot` (JSONB) et `exigences.preuves_chunks` (JSONB) sont **déjà** assez souples pour absorber les nouveaux besoins (résultats du Superviseur, sous-questions, citations par expert) sans migration — c'est une bonne nouvelle : le schéma initial avait anticipé ce genre d'évolution.

### 1.3 Une seule vraie nouvelle table : `retrieval_traces`

**Pourquoi une table, pas juste un JSONB de plus.** Avec la décomposition (jusqu'à 4 sous-questions) et jusqu'à 5 experts, **une seule** question utilisateur peut déclencher jusqu'à ~15-20 tentatives CRAG individuelles. Les entasser dans `generations.context_snapshot` rendrait impossible une requête simple du type *« quelle est la distribution des grades (Correct/Ambigu/Incorrect) par expert »* — exactement la métrique dont ton chapitre évaluation a besoin (`test.md` §2.8 : Recall@20, comparaisons dense/hybride/rerank). Une table dédiée, une ligne par tentative, se requête nativement en SQL.

C'est aussi la version base-de-données du principe d'observabilité que tu as déjà dans tes fiches (`IA_Agentique/10` §1.11, et le triplet Run/Trace/Thread de LangSmith en `/04`) — même besoin, implémenté ici directement en SQL plutôt que via une plateforme externe.

```sql
CREATE TABLE retrieval_traces (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Rattachement : au message qui a déclenché la recherche, et
    -- (une fois connue) à la génération qui en a résulté
    message_id          UUID REFERENCES messages(id) ON DELETE CASCADE,
    generation_id       UUID REFERENCES generations(id) ON DELETE SET NULL,

    -- Décomposition (§5.5) : 0 si la question n'était pas composée
    sous_question_index INTEGER NOT NULL DEFAULT 0,
    sous_question_texte TEXT,

    -- Quel expert, quelle tentative dans SA boucle CRAG
    expert              VARCHAR(16) NOT NULL
        CHECK (expert IN ('juridique','technique','financier','graphe','patrimoine')),
    tentative           INTEGER NOT NULL CHECK (tentative BETWEEN 1 AND 3),

    -- Ce qui a été cherché et comment
    query_utilisee      TEXT NOT NULL,
    filtres             JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Résultat du grading (§5.3)
    grade               VARCHAR(16) CHECK (grade IN ('correct','ambigu','incorrect')),
    grade_method        VARCHAR(16) CHECK (grade_method IN ('seuil','llm_juge')),
    chunks_retournes    JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{chunk_id, score}]

    abstention          BOOLEAN NOT NULL DEFAULT FALSE,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_traces_message ON retrieval_traces(message_id);
CREATE INDEX idx_traces_tenant_expert_grade ON retrieval_traces(tenant_id, expert, grade);
```

Exemple direct d'utilité pour ton mémoire (chapitre évaluation) :

```sql
-- Distribution des grades par expert (mesure la fiabilité de chaque expert)
SELECT expert, grade, count(*)
FROM retrieval_traces
GROUP BY expert, grade
ORDER BY expert;

-- Combien de fois une question a eu besoin de plus d'1 tentative
SELECT expert, avg(tentative) AS tentatives_moyennes
FROM retrieval_traces
GROUP BY expert;
```

### 1.4 Ce qui reste volontairement en JSONB (pas de nouvelle colonne)

| Besoin | Où | Pourquoi pas une colonne dédiée |
|---|---|---|
| Sortie complète du Superviseur (intent, is_compound, sous_questions, experts) | `messages.meta` (existant) | Structure qui peut évoluer (ex. futur `depends_on`, §8.4) sans migration à chaque changement de forme |
| Citations + contexte réellement envoyé au générateur | `generations.context_snapshot` (existant) | Déjà conçu pour ça, formaté par génération |
| `section_type_confidence` / `section_type_method` | `chunks.extra` (existant) | Audit seulement, jamais dans une clause `WHERE` |

### 1.5 Nouveau `doc_role='annexe'` — documents d'appoint scopés à un dossier

**Besoin** (soulevé en cours de conception) : pendant qu'on rédige une réponse à un AO, on veut pouvoir joindre un document qui aide **cette** rédaction — sans qu'il devienne automatiquement permanent dans le patrimoine partagé de tout le tenant, ni qu'il soit traité comme le DAO courant (extraction d'exigences).

```sql
ALTER TABLE documents
    ADD COLUMN dossier_id UUID REFERENCES dossiers(id) ON DELETE CASCADE;

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_doc_role_check;
ALTER TABLE documents ADD CONSTRAINT documents_doc_role_check
    CHECK (doc_role IN ('patrimoine', 'dao_courant', 'dao_archive', 'annexe'));

-- Une annexe DOIT être rattachée à un dossier, et rien d'autre ne le doit
ALTER TABLE documents ADD CONSTRAINT annexe_requires_dossier
    CHECK ( (doc_role = 'annexe') = (dossier_id IS NOT NULL) );

CREATE INDEX idx_documents_dossier ON documents(dossier_id) WHERE dossier_id IS NOT NULL;
```

**Effet sur le retrieval** (extension du filtre déjà défini par expert, `architecture_agentique_retrieval_generation.md` §1.1) — chaque expert ajoute, uniquement quand la conversation est liée à un dossier :

```text
filtre_expert = (filtre habituel de l'expert)
                OR (doc_role = 'annexe' AND documents.dossier_id = dossier_id_courant)
```

Une annexe reste invisible depuis toute autre conversation/dossier. Elle **ne passe pas** par `extract_graph` par défaut (document d'appoint, pas un enrichissement du graphe d'entreprise) — sauf promotion.

**Promotion vers le patrimoine** — réutilise un champ déjà prévu en V1 pour exactement ce rôle (`documents.dossier_origine_id`, documenté : *« un fichier de patrimoine issu d'un dossier déjà traité »*) :

```sql
UPDATE documents
SET doc_role = 'patrimoine', dossier_origine_id = dossier_id, dossier_id = NULL
WHERE id = :document_id;
-- puis enqueue extract_graph(document_id) si pas déjà fait
```

---

## 2. Interface actuelle : diagnostic (lu dans le code, pas supposé)

```text
frontend_ao/src/pages/
    ConversationsPage.tsx   628 lignes — chat + panneau preview markdown
    DocumentsPage.tsx       494 lignes — upload + statut ingestion
    DossiersPage.tsx         85 lignes — LISTE PLATE, export seulement
    LoginPage.tsx, RoleDashboard.tsx, admin/*
```

Ce que `DossiersPage.tsx` fait réellement aujourd'hui (lu intégralement) : une table à 5 colonnes (projet, client, réf. DAO, statut, échéance) + un bouton export. **Aucun clic ne mène nulle part** — pas de route de détail, pas d'onglet, pas de vue exigences/plan/review. `ConversationsPage.tsx` ne référence **jamais** `review`, `approve`, `regen`, `outline` ou `exigence` dans son code — tout le HITL décrit dans `pipeline_technique_detaille.md` (approve/edit/regen) **n'existe nulle part sur l'interface**, seulement dans le backend et la théorie des documents `Fichier/`.

**Diagnostic net** : ta remarque est confirmée par le code, pas juste une impression — l'interface expose le chat et l'upload, mais aucune des tables métier qui rendent le workflow AO réellement pilotable (exigences, plan, revue humaine) n'a d'écran.

**Bug trouvé en vérifiant le code (pas hypothétique) :** le bouton 📎 déjà présent dans `ConversationsPage.tsx` appelle `POST /conversations/{id}/documents`, et côté serveur (`app/api/conversations.py` ligne 318) le `doc_role` est **codé en dur à `"patrimoine"`**. Tout document joint en conversation devient donc aujourd'hui automatiquement et silencieusement permanent dans le patrimoine partagé de tout le tenant — c'est la cause racine exacte du problème signalé (upload d'un document d'appoint qui ne devrait pas polluer le patrimoine). Traité en §1.5 et §3.7.

---

## 3. Proposition d'architecture d'interface

### 3.1 Liste des dossiers — enrichie et groupée par entité (client)

*Ta question : « les dossiers de chaque entité pour qui on a fait le DAO »* — c'est `dossiers.client_name` (le maître d'ouvrage : SNCF, RATP…), pas le tenant (le tenant, c'est l'entreprise BTP qui utilise la plateforme — déjà isolé par l'auth, un tenant ne voit jamais les dossiers d'un autre).

```text
┌─────────────────────────────────────────────────────────────┐
│ Dossiers                              [+ Nouveau dossier]   │
│ Grouper par : [Client ▾]  Filtrer : [Statut ▾] [Échéance ▾] │
├─────────────────────────────────────────────────────────────┤
│ ▼ SNCF (3 dossiers)                                          │
│   Gare de Nantes          generating   12/15 ✅  5/8 sect.  │
│                                         1 ⚠️ éliminatoire    │
│   Gare de Lyon            exported     15/15 ✅  8/8 sect.  │
│   ...                                                        │
│ ▼ RATP (1 dossier)                                           │
│   Ligne 14 extension      draft        0/10     0/6         │
└─────────────────────────────────────────────────────────────┘
```

Deux indicateurs de santé ajoutés à chaque ligne (calculs simples, agrégats de tables déjà existantes, aucun nouveau champ) :
- **Couverture exigences** (`count(statut='couverte') / count(*)`, avec alerte rouge si un `obligatoire=true` est `non_couverte`) ;
- **Avancement du plan** (`count(status='approved') / count(*)` sur `outline_items`).

C'est ce qui manque aujourd'hui pour qu'un manager voie en un coup d'œil **où est le risque** (une exigence éliminatoire non couverte, à J-3 de l'échéance) sans ouvrir chaque dossier.

### 3.2 Page détail dossier — nouvelle route, 5 onglets

`/dossiers/:id`, actuellement inexistante. C'est le cœur du manque identifié.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Gare de Nantes — SNCF — Réf. 2024-045                     [Exporter ▾] │
│ [ Exigences ]  [ Plan ]  [ Sections ]  [ Documents ]  [ Historique ]     │
└─────────────────────────────────────────────────────────────────────────┘
```

L'onglet **Documents** (nouveau, cf. §1.5/§3.7) liste les annexes (`doc_role='annexe'`) rattachées à ce dossier, avec le bouton « ↑ Promouvoir au patrimoine » par ligne — distinct du DAO courant, lui-même affiché séparément.

### 3.3 Onglet Exigences — table `exigences`

```text
┌──────────────────────────────────────────────────────────────────┐
│ Libellé                    Type       Oblig.  Statut        Preuves│
├──────────────────────────────────────────────────────────────────┤
│ Certification ISO 9001     technique   ✓      🟢 couverte   [3]   │
│ 5 ans expérience ferrov.   technique   ✓      🟢 couverte   [2]   │
│ CA > 10M€                  financière  ✓      🔴 non_couv.  —     │
│ Délai < 18 mois            délai       ✓      🟡 à_revoir   [1]   │
└──────────────────────────────────────────────────────────────────┘
```

- Couleur = mapping direct de `exigences.statut` (`a_couvrir`→gris, `en_cours`→bleu, `couverte`→vert, `non_couverte`→rouge, `a_revoir`→orange).
- **Une ligne rouge sur une exigence `obligatoire=true` doit être visuellement impossible à manquer** (bandeau d'alerte en haut de la page, pas juste une couleur dans un tableau — c'est un risque d'élimination du marché).
- Colonne « Preuves » = clic → ouvre les chunks de `exigences.preuves_chunks`, avec leur texte et leur page (traçabilité déjà en base, jamais montrée).
- Bouton par ligne : « Relancer la recherche » → redéclenche la boucle CRAG (§5 du doc précédent) pour cette exigence spécifique si `non_couverte` — sans ça, une exigence bloquée reste bloquée indéfiniment.

### 3.4 Onglet Plan — table `outline_items`

```text
┌────────────────────────────────────────────────────────┐
│ #  Titre                        Statut       Actions    │
├────────────────────────────────────────────────────────┤
│ 1  Présentation entreprise      ✅ approuvée  [Voir]     │
│ 2  Compréhension mission        ✅ approuvée  [Voir]     │
│ 3  Moyens humains               🟡 générée    [Revoir]  │
│ 4  Moyens matériels             ⬜ todo        [Générer] │
│ 5  Références                   ⬜ todo        [Générer] │
└────────────────────────────────────────────────────────┘
[Générer toutes les sections restantes]
```

Mapping direct de `outline_items.status` (`todo`→⬜, `generated`→🟡 en attente de revue, `approved`→✅, `rejected`→🔴). Drag-and-drop de l'ordre (`sort_order`) — actuellement figé par le canevas par défaut, mais rien n'empêche un ajustement manuel si le RC impose un plan différent.

### 3.5 Onglet Sections — l'écran de revue HITL (le vrai trou)

C'est l'écran qui **n'existe nulle part aujourd'hui** — actuellement, approve/edit/regen n'a **aucune** interface, seulement une route API. Proposition, pour une section à l'état `generated` :

```text
┌──────────────────────────────────────────────────────────────────┐
│ 4. Moyens matériels                              v2 (2 versions) │
├──────────────────────────────────────────────────────────────────┤
│  Notre parc comprend 3 grues de 50 tonnes [1], utilisées         │
│  notamment sur le chantier de la gare de Bordeaux [2]...         │
│                                                                    │
│  ⚠️ Non trouvé : aucune référence de grue > 80 tonnes dans le    │
│     patrimoine (déclaré par l'expert Patrimoine, tentative 3/3)  │
├──────────────────────────────────────────────────────────────────┤
│  Sources : [1] CV_Grutier.pdf p.4 (expert: patrimoine)           │
│            [2] Ref_Bordeaux.pdf p.12 (expert: patrimoine)        │
├──────────────────────────────────────────────────────────────────┤
│  [ Approuver ]   [ Modifier le texte ]   [ Régénérer... ]        │
└──────────────────────────────────────────────────────────────────┘
```

Trois points de conception à ne pas rater :

1. **Les abstentions (`generations` / champ `abstentions` déjà en base) doivent être affichées explicitement**, pas juste absentes du texte — sinon le rédacteur ne sait pas qu'un aspect n'a pas été trouvé, et approuve une section incomplète sans le savoir. C'est la traduction UI directe du principe déjà posé : *« l'abstention n'est pas un échec à cacher »*.
2. **Chaque citation doit indiquer quel expert l'a trouvée** (`retrieval_traces.expert`, §1.3) — ça donne de la transparence sur le raisonnement multi-agents, utile autant pour la confiance de l'utilisateur que pour ton évaluation de mémoire (« l'expert graphe a-t-il été utile en pratique ? »).
3. **Régénérer** ouvre un champ de consigne (`reviews.regen_instruction`, déjà en base, jamais exposé) — pas un simple bouton, sinon l'utilisateur ne peut pas dire *« insiste sur les grues 50 t »* comme le prévoit déjà le parcours documenté (`architecture_synthese.md` §11).

### 3.6 Onglet Historique — `reviews` + versions de `generations`

```text
┌────────────────────────────────────────────────────────┐
│ v1 → régénérée par J.Dupont (2026-08-28)                │
│     "Insister sur les grues 50 t"                       │
│ v2 → approuvée par J.Dupont (2026-08-28)                │
└────────────────────────────────────────────────────────┘
```

Table `reviews` déjà entièrement modélisée pour ça (`action`, `comment`, `regen_instruction`, `user_id`, `created_at`) — c'est un simple affichage chronologique, aucune nouvelle donnée à produire.

### 3.7 Distinction annexe/patrimoine à l'upload — corriger le point de friction actuel (§1.5)

**Au moment du 📎 dans le chat** — c'est ici que le bug (§2) doit être corrigé : au lieu d'un `doc_role` figé côté serveur, un choix explicite et visible.

```text
┌─────────────────────────────────────────────────────────────┐
│ 📎 CCTP_addendum.pdf                                         │
│                                                               │
│ Comment utiliser ce document ?                               │
│                                                               │
│ ● Aide ponctuelle pour CE dossier uniquement                │
│   Sert à vous aider à rédiger ce dossier. Invisible depuis  │
│   les autres dossiers, non conservé dans le patrimoine.      │
│                                                               │
│ ○ Ajouter au patrimoine de l'entreprise                      │
│   Utilisable pour TOUS les futurs dossiers. À réserver aux  │
│   documents de référence validés (méthodo, certifs, CV...). │
│                                                               │
│                                          [Annuler] [Confirmer]│
└─────────────────────────────────────────────────────────────┘
```

Défaut : présélectionné sur « Aide ponctuelle » (`annexe`) si la conversation est liée à un dossier — le choix le moins engageant par défaut. Si la conversation n'a pas de dossier (Q&A libre sur le patrimoine), ce choix n'a pas lieu d'être affiché : `patrimoine` reste le seul sens possible.

**Indicateur permanent**, pour ne pas perdre de vue ce qui est attaché à quel titre :

```text
┌─ Documents de ce dossier ──────────────────┐
│ 📎 CCTP_addendum.pdf        [ponctuel] [↑ Promouvoir]
│ 📄 DAO_Gare_Nantes.pdf      [DAO courant]
└──────────────────────────────────────────────┘
```

Le bouton « ↑ Promouvoir » n'existe que sur les documents `annexe` (action explicite, jamais implicite — §1.5).

**`DocumentsPage.tsx`** — le sélecteur existant (« Patrimoine (références) » / « DAO courant ») devient descriptif au lieu de silencieux sur la conséquence :

```text
Rôle du document : [ Patrimoine (références) ▾ ]
ⓘ Visible et cherché dans TOUS les futurs dossiers de l'entreprise.
  Réservé aux documents de référence validés.
```

```text
Rôle du document : [ Annexe d'un dossier ▾ ]
  Dossier concerné : [ Gare de Nantes — SNCF ▾ ]
ⓘ Visible UNIQUEMENT dans ce dossier. Ne sera jamais utilisé pour
  répondre à un autre appel d'offres.
```

---

## 4. Endpoints API nécessaires (état actuel : squelette, per `JOURNAL.md`)

| Endpoint | Rôle | Statut actuel |
|---|---|---|
| `GET /dossiers/{id}` | Détail complet (dossier + compteurs exigences/plan) | À créer |
| `GET /dossiers/{id}/exigences` | Table §3.3 | À créer |
| `GET /dossiers/{id}/outline` | Table §3.4 | À créer |
| `POST /dossiers/{id}/sections/{key}/generate` | Déclenche le pipeline agentique pour 1 section | Squelette existant, à connecter |
| `POST /dossiers/{id}/sections/{key}/review` | `{action: approve\|edit\|regen, text?, instruction?}` | Documenté (`pipeline_technique_detaille.md`), jamais implémenté |
| `GET /dossiers/{id}/sections/{key}/versions` | Historique §3.6 | À créer |
| `POST /exigences/{id}/recherche` | Relance la boucle CRAG pour 1 exigence (§3.3) | À créer |

---

## 5. Dossier administratif, checklist de pièces et upload d'images

**Périmètre confirmé** : le système doit produire les 3 dossiers d'une offre (technique, financier, administratif), et servir de stockage pour les pièces. Le financier reste hors génération de prose (calcul + remplissage de gabarit, §3.6 du document précédent — pas traité ici). L'administratif, en revanche, est une vraie checklist à modéliser.

### 5.1 Bug trouvé : l'upload d'image plante aujourd'hui

Vérifié dans `backend_ao/app/ingest/parse.py` : `parse_file()` (lignes 32-53) ne route que `.xlsx/.docx/.txt/.md/.pdf` — un `.jpg`/`.png` tombe dans le fallback qui tente de décoder les octets binaires en UTF-8 et lève `ValueError("Format non géré")`. **Bonne nouvelle** : le moteur OCR sait déjà traiter une image directe (`_paddle_run`, ligne 246 : `_paddle_ocr_pages(ocr, [(1, path)], ...)` quand l'entrée n'est pas un PDF) — le trou n'est que le routage, pas l'OCR lui-même.

```python
# Ajout minimal dans parse_file() — réutilise le moteur OCR existant tel quel
if suffix in {".jpg", ".jpeg", ".png", ".tiff", ".webp"}:
    log.info("route parse → image directe (%s)", filename)
    return _try_paddle(path) or ParsedDocument(pages=[], parser="image-sans-texte", page_count=0)
```

### 5.2 Deux natures d'image — ne pas les traiter pareil

| | Image = document texte scanné (KBIS, attestation) | Image = actif visuel (photo chantier, logo) |
|---|---|---|
| Traitement | OCR → texte ≥ seuil (40 car., seuil déjà existant ailleurs) → chunké/embeddé normalement | OCR → peu/pas de texte → **pas un échec** : `status='ready'`, **zéro chunk** |
| Signal en base | Chunks présents | Absence de chunk = signal suffisant, pas de nouvelle colonne nécessaire |
| Usage | Recherche texte normale (RAG) | Insertion directe dans l'export DOCX, jamais cherchée en texte |

### 5.3 Checklist administrative — nouvelle table

Sémantique différente de `exigences` (qui prouve une **affirmation textuelle** par un chunk) : ici on attache un **document entier**.

```sql
CREATE TABLE dossier_pieces (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id    UUID NOT NULL REFERENCES dossiers(id) ON DELETE CASCADE,
    libelle       VARCHAR(255) NOT NULL,
    obligatoire   BOOLEAN NOT NULL DEFAULT TRUE,
    document_id   UUID REFERENCES documents(id) ON DELETE SET NULL,
    statut        VARCHAR(32) NOT NULL DEFAULT 'manquant'
        CHECK (statut IN ('manquant','trouve_patrimoine','a_uploader','fourni')),
    source        VARCHAR(16) DEFAULT 'rc' CHECK (source IN ('rc','standard')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

```text
1. extract_checklist_administrative(dossier_id)  ← déterministe, même famille que
   extract_outline (§9 doc précédent) : scanne le RC, sinon fallback liste standard
   (KBIS, attestations fiscale/sociale, assurance décennale, DC1/DC2...)
2. Pour chaque pièce : cherche un document valide en patrimoine (doc_type='administratif')
   → trouvé : statut='trouve_patrimoine' ; sinon : statut='manquant'
3. UI : bouton "Choisir dans le patrimoine" ou "Uploader" (PDF ou image, §5.1) par pièce
4. Toutes les obligatoires à 'fourni' → dossier administratif complet
```

### 5.4 Insertion d'images dans l'export — placement toujours confirmé par un humain

Extension du contrat `SectionGeneree` :

```python
class Bloc(BaseModel):
    type: Literal["paragraphe", "liste", "tableau_md", "sous_titre", "image"]
    document_id: str | None = None   # requis si type="image"
    texte: str
```

**Décision de conception** : le LLM ne choisit jamais seul quelle image insérer où — même logique que les citations (proposer, jamais décider seul sur un fait non vérifiable automatiquement). Un nouvel outil `retrieve_images(query)` peut **suggérer** des candidats (recherche par nom de fichier/légende) à l'écran de revue (§3.5), mais le placement final est confirmé par un clic humain — une image mal choisie automatiquement est plus difficile à détecter qu'une mauvaise citation textuelle.

---

## 6. Récapitulatif des décisions à valider

| # | Décision | Proposition | Statut |
|---|---|---|---|
| 1 | Suppression de table | Aucune | ✅ Validé |
| 2 | `chunks.section_type` en colonne dédiée (pas JSONB) | Oui, indexée — filtrée à chaque requête expert | ✅ Validé |
| 3 | `generations.summary_short` | Colonne ajoutée | ✅ Validé |
| 4 | Nouvelle table `retrieval_traces` | Oui — observabilité + métriques d'évaluation mémoire | ✅ Validé |
| 5 | Groupement des dossiers par `client_name` | Oui, avec indicateurs de couverture/avancement | ✅ Validé |
| 6 | Écran de revue HITL (approve/edit/regen) | Nouvel onglet Sections, avec abstentions et attribution par expert visibles | ✅ Validé |
| 7 | `doc_role='annexe'` + `documents.dossier_id`, choix explicite à l'upload en chat | Corrige le bug trouvé (`doc_role` figé à `"patrimoine"` côté serveur) — §1.5, §3.7 | À confirmer |
| 8 | Routage image dans `parse_file()` + distinction texte-scanné/actif-visuel | §5.1, §5.2 — corrige le bug d'upload image trouvé | À confirmer |
| 9 | Table `dossier_pieces` (checklist administrative) | §5.3 | À confirmer |
| 10 | Bloc `type="image"` + placement toujours humain (jamais le LLM seul) | §5.4 | À confirmer |

---

## Liens

- `Nouvelle_Architecture/architecture_agentique_retrieval_generation.md` — le pipeline que cette interface doit exposer
- `Fichier/champsdeBase_et_contraites_workflow.md` — schéma SQL de référence
- `frontend_ao/src/pages/DossiersPage.tsx`, `ConversationsPage.tsx` — état actuel lu pour ce diagnostic
