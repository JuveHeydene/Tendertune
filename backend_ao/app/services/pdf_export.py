"""Export PDF « habillé » — rendu HTML/CSS (template Jinja2) via WeasyPrint,
en remplacement d'un export ReportLab plat. Réutilise les blocs structurés
(SectionGeneree, cf. app/models/pydantic.py) plutôt que le texte aplati
utilisé par les exports docx/md/txt : listes et tableaux markdown sont donc
rendus comme de vraies listes/tableaux HTML, pas comme du texte brut."""

from __future__ import annotations

import html as html_lib
from datetime import UTC, datetime
from pathlib import Path

import markdown as md_lib
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _render_bloc_html(bloc: dict) -> str:
    btype = bloc.get("type")
    texte = (bloc.get("texte") or "").strip()
    if not texte:
        return ""

    if btype == "sous_titre":
        level = min(max(bloc.get("heading_level") or 3, 2), 3)
        return f"<h{level}>{html_lib.escape(texte)}</h{level}>"

    if btype == "liste":
        items = [line.strip().lstrip("-").strip() for line in texte.split("\n") if line.strip()]
        lis = "".join(f"<li>{html_lib.escape(item)}</li>" for item in items)
        return f"<ul>{lis}</ul>" if lis else ""

    if btype == "tableau_md":
        return md_lib.markdown(texte, extensions=["tables"])

    if btype == "image":
        ref = html_lib.escape(bloc.get("document_id") or "?")
        return (
            '<div class="image-placeholder">'
            f"Image proposée ({ref}) — insertion à confirmer en revue"
            "</div>"
        )

    # paragraphe (par défaut)
    paras = [p.strip() for p in texte.split("\n") if p.strip()]
    return "".join(f"<p>{html_lib.escape(p)}</p>" for p in paras)


def sections_from_pairs(pairs) -> list[dict]:
    """`pairs` : résultat de `latest_sections` (OutlineItem, Generation | None).
    Ignore les items sans génération, comme le fait déjà `_section_rows`."""
    sections: list[dict] = []
    for item, gen in pairs:
        if gen is None:
            continue
        content = gen.content or {}
        titre = content.get("titre") or item.title
        blocs = content.get("blocs")
        if blocs:
            blocks_html = [h for b in blocs if (h := _render_bloc_html(b))]
        else:
            # Compat V1 : contenu {"titre", "texte"} sans blocs structurés.
            texte = content.get("texte") or ""
            blocks_html = [f"<p>{html_lib.escape(p.strip())}</p>" for p in texte.split("\n") if p.strip()]
        sections.append(
            {
                "key": item.key,
                "titre": titre,
                "blocks_html": blocks_html,
                "abstentions": content.get("abstentions") or [],
            }
        )
    return sections


def render_memoire_html(
    *,
    project_name: str,
    sections: list[dict],
    transcript: str | None,
    version: int = 1,
) -> str:
    if not sections and transcript:
        paras = [p.strip() for p in transcript.split("\n") if p.strip()]
        sections = [
            {
                "key": "brouillon",
                "titre": "Brouillon",
                "blocks_html": [f"<p>{html_lib.escape(p)}</p>" for p in paras],
                "abstentions": [],
            }
        ]
    template = _env.get_template("memoire_export.html")
    return template.render(
        project_name=project_name or "Mémoire technique",
        sections=sections,
        section_count=len(sections),
        version=version,
        generated_at=datetime.now(UTC).strftime("%d/%m/%Y"),
    )


def build_pdf(
    *,
    project_name: str,
    sections: list[dict],
    transcript: str | None,
    version: int = 1,
) -> bytes:
    from weasyprint import HTML  # import différé — dépendance système (pango/cairo)

    html = render_memoire_html(
        project_name=project_name, sections=sections, transcript=transcript, version=version
    )
    return HTML(string=html).write_pdf()
