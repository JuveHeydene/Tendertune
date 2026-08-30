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


class DocType(str, Enum):
    rc = "rc"
    cctp = "cctp"
    ccap = "ccap"
    memoire = "memoire"
    reference = "reference"
    scan = "scan"
    dpgf = "dpgf"
    bpu = "bpu"
    autre = "autre"


class Bloc(BaseModel):
    type: Literal["paragraphe", "liste", "tableau_md", "sous_titre"]
    heading_level: int | None = None
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
