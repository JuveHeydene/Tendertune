"""Contrats de données V1 — le LLM remplit ces schémas, pas du texte libre."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    needs_review = "needs_review"


class DocRole(str, Enum):
    patrimoine = "patrimoine"
    dao_courant = "dao_courant"
    dao_archive = "dao_archive"
    # V2 — pièce d'appoint scopée à UN dossier, jamais dans le patrimoine partagé
    # (Nouvelle_Architecture/base_de_donnees_et_interface.md §1.5)
    annexe = "annexe"


class DocType(str, Enum):
    rc = "rc"
    cctp = "cctp"
    ccap = "ccap"
    memoire = "memoire"
    reference = "reference"
    scan = "scan"
    dpgf = "dpgf"
    bpu = "bpu"
    # V2 — pièces de la checklist administrative (§5.3)
    administratif = "administratif"
    autre = "autre"


class SectionType(str, Enum):
    """V2 — classification dynamique du chunk (§3.1), signal DOUX pour le
    routage des experts. Jamais un filtre bloquant : voir CRAG (Ambigu → élargir)."""

    rc = "rc"
    ccap = "ccap"
    cctp = "cctp"
    dpgf = "dpgf"
    bpu = "bpu"
    memoire = "memoire"
    reference = "reference"
    autre = "autre"


class Archetype(str, Enum):
    """V2 — spécialisation déterministe du prompt de génération (§10) :
    lookup sur outline_items.archetype, jamais une décision d'agent."""

    institutionnelle = "institutionnelle"
    factuelle = "factuelle"
    narrative = "narrative"
    conformite = "conformite"


class Expert(str, Enum):
    """V2 — agents de RÉCUPÉRATION uniquement (§1.1) : ils ne rédigent jamais,
    un seul générateur centralisé écrit le SectionGeneree final."""

    juridique = "juridique"
    technique = "technique"
    financier = "financier"
    graphe = "graphe"
    patrimoine = "patrimoine"


class Grade(str, Enum):
    """V2 — sortie de grade_context (CRAG, §5.3)."""

    correct = "correct"
    ambigu = "ambigu"
    incorrect = "incorrect"


class Bloc(BaseModel):
    type: Literal["paragraphe", "liste", "tableau_md", "sous_titre", "image"]
    heading_level: int | None = None
    # V2 — requis si type="image". Le LLM peut le proposer via retrieve_images(),
    # mais le placement est TOUJOURS confirmé par un humain (§5.4) — jamais
    # inséré automatiquement dans l'export sans validation HITL.
    document_id: str | None = None
    texte: str


class ExtraitCite(BaseModel):
    chunk_id: str
    score: float
    page: int | None = None
    texte: str
    heading_path: str | None = None


class Exigence(BaseModel):
    id: str
    libelle: str
    type: str
    obligatoire: bool = True
    page_source: int | None = None
    statut: str = "todo"


class SectionGeneree(BaseModel):
    section_key: str
    titre: str
    blocs: list[Bloc]
    citations: list[str] = Field(default_factory=list)
    exigences_couvertes: list[str] = Field(default_factory=list)
    abstentions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# V2 — Superviseur / Router (Nouvelle_Architecture/architecture_agentique_
# retrieval_generation.md §8). Schéma STRICT, aucun champ improvisé.
# ---------------------------------------------------------------------------


class Intent(str, Enum):
    smalltalk = "smalltalk"
    export = "export"
    clarification_needed = "clarification_needed"
    hybrid_rag = "hybrid_rag"
    run_section = "run_section"


class Complexite(str, Enum):
    simple = "simple"
    complexe = "complexe"


class SousQuestion(BaseModel):
    """Une sous-question du Superviseur. `experts=[]` est UNE VALEUR VALIDE
    (règle R9) : le contenu nécessaire est déjà fourni par l'utilisateur ou
    déjà établi dans l'historique — aucune recherche n'est alors tentée, et
    ce n'est PAS une abstention (§5.4)."""

    texte: str
    experts: list[Expert] = Field(default_factory=list)
    complexite: Complexite = Complexite.simple


class SuperviseurOutput(BaseModel):
    """Sortie JSON contrainte du nœud Superviseur — 1 seul appel LLM,
    température 0. Règles R1-R9 détaillées en §8.2 du document de référence."""

    intent: Intent
    is_compound: bool = False
    sous_questions: list[SousQuestion] = Field(default_factory=list, max_length=4)
    message_clarification: str | None = None


class SourceContexte(str, Enum):
    """Distinction posée en §5.4 — ne JAMAIS confondre les deux derniers cas :
    l'un est un échec de recherche (à signaler), l'autre est une absence
    volontaire de recherche (rien à signaler)."""

    retrieval = "retrieval"
    abstention = "abstention"
    conversation = "conversation"


class ResultatExpert(BaseModel):
    """Ce qu'un expert remonte à l'agrégateur après sa boucle CRAG (§5.2).
    Un expert ne rédige JAMAIS — il ne renvoie que du contexte brut."""

    expert: Expert
    source: SourceContexte
    chunks: list[ExtraitCite] = Field(default_factory=list)
    relations_graphe: list[dict] = Field(default_factory=list)
    tentatives: int = 0
    raison_abstention: str | None = None


class DecisionHumaine(str, Enum):
    approve = "approve"
    edit = "edit"
    regen = "regen"


class ReviewAction(BaseModel):
    action: DecisionHumaine
    text: str | None = None
    comment: str | None = None


class MessageCreate(BaseModel):
    text: str


class Chunk(BaseModel):
    id: str
    document_id: str
    parent_id: str | None = None
    text: str
    heading_path: str | None = None
    page: int | None = None
    token_count: int | None = None


class ParentChunk(Chunk):
    children_ids: list[str] = Field(default_factory=list)


class DocumentIngested(BaseModel):
    file_id: str
    hash: str
    doc_type: DocType
    pages: list[dict]
    heading_tree: list[dict] = Field(default_factory=list)
    ocr_used: bool = False
    ocr_confidence_avg: float | None = None
