"""Requêtes Cypher paramétrées — Diagramme 4, §4.7.

Jamais de Cypher généré librement par un LLM (règle posée en conception,
tableau §7 point #6) : le LLM extrait des entités (tâche bornée), LE CODE
construit la requête à partir de ces templates fixes. Le schéma de graphe
est fermé (ENTITY_TYPES/REL_TYPES, app/graph/extract.py) : une poignée de
templates 1-2 sauts couvre l'espace réel des questions relationnelles AO.
"""

from __future__ import annotations

# 1-hop générique : "qui est lié à X ?"
ONE_HOP = """
MATCH (e:Entity {key: $key})-[r:REL]-(o:Entity)
RETURN o.key AS other_key, o.name AS other_name, o.type AS other_type,
       r.type AS rel_type, r.source_chunk_id AS source_chunk_id
LIMIT 25
"""

# 1-2 sauts bornés : conformité ("quelle certif couvre quelle exigence")
BOUNDED_TWO_HOP = """
MATCH (e:Entity {key: $key})-[r:REL*1..2]-(o:Entity)
WHERE ALL(rel IN r WHERE rel.type IN $rel_types)
RETURN o.key AS other_key, o.name AS other_name, o.type AS other_type,
       [rel IN r | rel.type] AS rel_types,
       [rel IN r | rel.source_chunk_id] AS source_chunk_ids
LIMIT 25
"""

# 2 ancres : "quel lien entre X et Y ?"
TWO_ANCHORS = """
MATCH (a:Entity {key: $key1})-[r:REL*1..2]-(b:Entity {key: $key2})
RETURN [rel IN r | rel.type] AS rel_types,
       [rel IN r | rel.source_chunk_id] AS source_chunk_ids
LIMIT 10
"""

CONFORMITE_REL_TYPES = ["SATISFAITE_PAR", "DETIENT", "CONTIENT"]
