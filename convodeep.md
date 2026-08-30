

Je vais vous expliquer concrètement comment cela fonctionne, et surtout, comment l'implémenter, y compris avec un LLM local.

1. Le Principe Fondamental : Le LLM ne développe pas de "mains"
C'est une erreur de penser que le LLM "apprend" à utiliser des outils. Le LLM ne fait que générer du texte. La magie opère grâce à un orchestrateur (que vous codez) qui interprète la sortie du LLM et agit en conséquence.

Le Processus "ReAct" (Reasoning + Acting)
Le paradigme ReAct (Yao et al., 2022) est la base de tous les systèmes agentiques modernes. Il alterne raisonnement (Thought) et action (Action) en boucle.

text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LE CYCLE ReAct D'UN AGENT                               │
│                                                                             │
│  Question: "Quelle est la clause de pénalité du contrat SNCF ?"           │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Thought: "Je dois trouver le contrat SNCF dans les documents."    │   │
│  │  Action: search_documents("contrat SNCF")                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Observation: "J'ai trouvé 3 documents : 'contrat_sncf_2024.pdf'..."│   │
│  │  Thought: "Je dois ouvrir ce document pour trouver la clause."     │   │
│  │  Action: read_document("contrat_sncf_2024.pdf")                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Observation: "Le document contient l'article 8 sur les pénalités."│   │
│  │  Thought: "J'ai trouvé la clause. Je peux répondre."               │   │
│  │  Final Answer: "La clause de pénalité est de 1/1000 par jour..."   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
Ce n'est pas le LLM qui "décide" d'utiliser un outil. C'est votre code qui :

Envoie au LLM une liste d'outils disponibles (dans le prompt).

Parse la réponse du LLM pour détecter s'il demande l'utilisation d'un outil.

Exécute l'outil.

Renvoie le résultat au LLM.

Répète jusqu'à ce que le LLM donne une réponse finale.

2. Le Prompt qui Rend Tout Possible
La clé est le prompt système. Vous devez donner au LLM des instructions claires sur comment formater sa demande d'outil.

text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PROMPT SYSTÈME POUR UN AGENT ReAct                      │
│                                                                             │
│  Tu es un assistant spécialisé dans les appels d'offres.                   │
│  Tu dois répondre aux questions en utilisant les outils disponibles.       │
│                                                                             │
│  FORMAT DE RÉPONSE :                                                       │
│  ─────────────────                                                         │
│  Pour utiliser un outil, réponds UNIQUEMENT au format :                    │
│  ```json                                                                    │
│  {"action": "nom_outil", "arguments": {"param1": "valeur1"}}              │
│  ```                                                                        │
│                                                                             │
│  Si tu as suffisamment d'informations pour répondre, réponds au format :   │
│  ```json                                                                    │
│  {"final_answer": "Ta réponse complète..."}                               │
│  ```                                                                        │
│                                                                             │
│  OUTILS DISPONIBLES :                                                      │
│  ─────────────────                                                         │
│  1. search_documents(query): Recherche des documents par similarité.       │
│  2. get_document_content(doc_id): Récupère le contenu d'un document.       │
│  3. search_graph(entity_type, entity_name): Cherche des relations dans Neo4j.│
│  4. get_project_details(project_name): Récupère les détails d'un projet.   │
│  5. search_sql(sql_query): Exécute une requête SQL sur les métadonnées.   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
3. L'Implémentation : Le Cœur de l'Orchestrateur
Voici un code Python fonctionnel qui implémente cet agent ReAct. Il est conçu pour être compatible avec un LLM local (Ollama, etc.).

python
# agent.py
import json
import re
from typing import Dict, Any, List, Optional, Callable
import ollama  # ou votre client LLM

class Tool:
    """Représente un outil que l'agent peut utiliser."""
    def __init__(self, name: str, description: str, function: Callable, parameters: Dict):
        self.name = name
        self.description = description
        self.function = function
        self.parameters = parameters  # Schema JSON des paramètres

class ReActAgent:
    """
    Un agent simple implémentant le paradigme ReAct (Reasoning + Acting).
    
    Il alterne :
    1. Demander au LLM une pensée (Thought) et une action (Action)
    2. Exécuter l'action (un outil)
    3. Observer le résultat (Observation)
    4. Répéter jusqu'à avoir une réponse finale
    """
    
    def __init__(self, llm_model: str, tools: List[Tool], max_iterations: int = 8):
        self.llm_model = llm_model
        self.tools = {tool.name: tool for tool in tools}
        self.max_iterations = max_iterations
        self.observations = []
    
    def _get_system_prompt(self) -> str:
        """Construit le prompt système avec la liste des outils."""
        tools_desc = "\n".join([
            f"- {name}: {tool.description}" 
            for name, tool in self.tools.items()
        ])
        
        return f"""
Tu es un assistant expert en appels d'offres BTP.

Tu disposes des outils suivants :
{tools_desc}

Pour utiliser un outil, réponds UNIQUEMENT au format JSON :
{{"action": "nom_outil", "arguments": {{"param1": "valeur1"}}}}

Si tu as suffisamment d'informations, réponds au format :
{{"final_answer": "Ta réponse..."}}

Ne fais jamais d'invention. Si tu ne sais pas, utilise un outil pour trouver.
"""
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse la réponse du LLM pour extraire l'action ou la réponse finale."""
        # Essayer d'extraire du JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_match:
            # Fallback : si le LLM ne répond pas en JSON, on le redirige
            return {"action": "ask_llm", "arguments": {"clarification": response}}
        
        try:
            data = json.loads(json_match.group())
            return data
        except json.JSONDecodeError:
            return {"action": "ask_llm", "arguments": {"clarification": response}}
    
    def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Appelle le LLM (local ou API)."""
        # Version avec Ollama (local)
        response = ollama.chat(
            model=self.llm_model,
            messages=messages,
            stream=False
        )
        return response['message']['content']
    
    def run(self, query: str) -> str:
        """Exécute l'agent sur une requête."""
        # 1. Initialiser l'historique des messages
        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": query}
        ]
        
        iteration = 0
        
        while iteration < self.max_iterations:
            iteration += 1
            print(f"🔄 Itération {iteration}")
            
            # 2. Appeler le LLM
            response = self._call_llm(messages)
            print(f"💬 LLM: {response[:200]}...")
            
            # 3. Parser la réponse
            parsed = self._parse_response(response)
            
            # 4. Vérifier si c'est une réponse finale
            if "final_answer" in parsed:
                return parsed["final_answer"]
            
            # 5. Sinon, c'est une action à exécuter
            action = parsed.get("action")
            arguments = parsed.get("arguments", {})
            
            if not action or action not in self.tools:
                # Si l'action n'est pas reconnue, on demande une clarification
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user", 
                    "content": f"Action '{action}' non reconnue. Utilise un des outils : {', '.join(self.tools.keys())}"
                })
                continue
            
            # 6. Exécuter l'outil
            tool = self.tools[action]
            try:
                result = tool.function(**arguments)
                print(f"🔧 {action}: {str(result)[:200]}...")
            except Exception as e:
                result = f"Erreur lors de l'exécution de {action}: {str(e)}"
                print(f"❌ {result}")
            
            # 7. Ajouter l'observation au contexte
            observation = f"Observation (résultat de {action}): {result}"
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": observation})
            
            # 8. Limiter la taille de l'historique pour éviter l'explosion du contexte
            if len(messages) > 20:
                messages = [messages[0]] + messages[-18:]
        
        # 9. Si on a atteint la limite d'itérations
        return "Je n'ai pas pu trouver de réponse satisfaisante. Pouvez-vous reformuler votre question ou me donner plus d'indices ?"
4. Les Outils pour Votre Système
Voici des exemples concrets d'outils que vous pouvez fournir à votre agent pour qu'il interagisse avec votre système :

python
# tools.py

from app.services import DocumentService, DossierService, Neo4jService

def search_documents(query: str, tenant_id: str = None, limit: int = 5) -> str:
    """
    Recherche des documents par similarité sémantique.
    
    Args:
        query: La requête de recherche.
        tenant_id: ID du tenant pour l'isolation.
        limit: Nombre de résultats à retourner.
    
    Returns:
        Une chaîne formatée avec les documents trouvés.
    """
    results = DocumentService.hybrid_search(query, tenant_id, limit=limit)
    
    if not results:
        return "Aucun document trouvé pour cette recherche."
    
    output = "Documents trouvés :\n"
    for i, doc in enumerate(results, 1):
        output += f"{i}. {doc.filename} (score: {doc.score:.2f})\n"
        output += f"   Extrait: {doc.text[:300]}...\n"
    
    return output

def get_document_content(doc_id: str) -> str:
    """
    Récupère le contenu complet d'un document.
    
    Args:
        doc_id: L'identifiant du document.
    
    Returns:
        Le contenu du document.
    """
    doc = DocumentService.get_document(doc_id)
    if not doc:
        return f"Document {doc_id} introuvable."
    
    return f"Contenu du document {doc.filename}:\n\n{doc.full_text}"

def search_graph(entity_type: str, entity_name: str) -> str:
    """
    Recherche des relations dans le graphe Neo4j.
    
    Args:
        entity_type: Type d'entité (ENTREPRISE, PROJET, CLIENT, etc.)
        entity_name: Nom de l'entité.
    
    Returns:
        Les relations trouvées.
    """
    results = Neo4jService.find_relations(entity_type, entity_name)
    
    if not results:
        return f"Aucune relation trouvée pour {entity_type} '{entity_name}'."
    
    output = f"Relations pour {entity_type} '{entity_name}':\n"
    for rel in results:
        output += f"- {rel.source_type} {rel.source_name} {rel.type} {rel.target_type} {rel.target_name}\n"
    
    return output

def search_sql(sql_query: str) -> str:
    """
    Exécute une requête SQL sur les métadonnées.
    
    Args:
        sql_query: La requête SQL à exécuter.
    
    Returns:
        Les résultats formatés.
    """
    # ⚠️ ATTENTION : Validation stricte pour éviter les injections SQL
    if not sql_query.lower().startswith("select"):
        return "Seules les requêtes SELECT sont autorisées."
    
    results = DocumentService.execute_query(sql_query)
    return str(results)

# ============================================================
# CREATION DES OUTILS
# ============================================================

tools = [
    Tool(
        name="search_documents",
        description="Recherche des documents par similarité sémantique. Utilise pour trouver des clauses, des références, ou des informations générales.",
        function=search_documents,
        parameters={"query": "string", "tenant_id": "string", "limit": "integer"}
    ),
    Tool(
        name="get_document_content",
        description="Récupère le contenu complet d'un document spécifique. Utilise quand tu as besoin d'analyser un document en détail.",
        function=get_document_content,
        parameters={"doc_id": "string"}
    ),
    Tool(
        name="search_graph",
        description="Cherche des relations dans le graphe de connaissances. Utilise pour trouver des liens entre projets, entreprises, certifications, etc.",
        function=search_graph,
        parameters={"entity_type": "string", "entity_name": "string"}
    ),
    Tool(
        name="search_sql",
        description="Exécute une requête SQL sur les métadonnées des documents. Utilise pour des questions précises sur les dates, montants, etc.",
        function=search_sql,
        parameters={"sql_query": "string"}
    ),
]

# ============================================================
# UTILISATION
# ============================================================

agent = ReActAgent(
    llm_model="llama3.1:8b",  # Ou "mistral:7b", "phi3:14b", etc.
    tools=tools,
    max_iterations=6
)

response = agent.run("Quelle est la clause de pénalité pour le contrat SNCF ?")
print(f"✅ Réponse finale: {response}")
5. Questions Fréquentes sur les LLM Locaux
5.1. Peut-on faire ça avec un LLM local ?
OUI, absolument. Les modèles locaux (Llama 3.1, Mistral, Qwen, Phi-3) sont parfaitement capables de suivre des prompts structurés et de générer du JSON.

5.2. Quels modèles locaux recommandez-vous ?
Modèle	Taille	Recommandation	Raison
Llama 3.1 8B	8B	⭐⭐⭐⭐⭐	Meilleur équilibre performance/qualité
Mistral 7B	7B	⭐⭐⭐⭐	Excellent suivi d'instructions
Qwen 2.5 7B	7B	⭐⭐⭐⭐	Très bon multilingue
Phi-3.5-MoE	14B (MoE)	⭐⭐⭐⭐	Rapide, économique
Mixtral 8x7B	46B (MoE)	⭐⭐⭐⭐⭐	Qualité proche de GPT-3.5
5.3. Le modèle local "reasonne" vraiment ?
Le modèle local fait exactement ce que ferait un modèle API : il complète du texte à partir du prompt. La différence est que vous contrôlez le prompt (le système et l'historique des messages). C'est votre code, pas le modèle, qui gère la boucle et exécute les outils.

5.4. Quels sont les risques ?
Context Overflow : L'historique des itérations peut devenir très long. Gérez la taille du contexte.

Hallucination d'outils : Le LLM peut inventer des actions. Validez toujours.

Boucle infinie : Un limiteur d'itérations est obligatoire.

Performance : Les modèles locaux sont plus lents et plus gourmands en mémoire.

6. Synthèse pour Votre V2
Votre application V1 est un système RAG déterministe. La V2 deviendra un système agentique :

text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ÉVOLUTION VERS LA V2                                    │
│                                                                             │
│  V1 (actuel)                    V2 (future)                                │
│  ───────────────────────        ───────────────────────────────────────────│
│  Pipeline linéaire              Boucle ReAct (itérative)                   │
│  Une seule recherche            Multiples recherches si besoin             │
│  Pas de raisonnement            Raisonnement explicite (Thought)           │
│  Pas d'outils                   Outils spécialisés (RAG, SQL, Graphe)     │
│  Pas de mémoire                 Mémoire des actions et observations        │
│  Déterministe                   Adaptatif                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
Ce qui change dans le code :
L'orchestrateur : Au lieu d'un graph LangGraph linéaire, vous implémentez une boucle ReAct.

Les outils : Vous exposez des fonctions (recherche, SQL, graphe) au LLM via le prompt.

Le LLM : Vous utilisez le même LLM, mais avec un prompt système structuré pour ReAct.

Ce qui NE CHANGE PAS :
Vos modèles d'embedding (BGE-M3).

Vos bases de données (Qdrant, PostgreSQL, Neo4j).

Votre logique métier (documents, dossiers, exigences).

Votre workflow d'ingestion (Docling, chunks, indexation).

7. Conclusion
Un système agentique ReAct est parfaitement réalisable avec un LLM local. Il repose sur :

Un prompt système structuré qui explique le format de réponse.

Un orchestrateur qui parse les réponses et exécute les outils.

Une boucle qui itère jusqu'à la réponse finale.

Des outils qui exposent les capacités de votre système (recherche, SQL, graphe).

L'agent n'acquiert pas de "mains magiques". C'est votre code qui lui donne la capacité de "faire" des choses en interprétant son texte. La complexité est dans l'orchestration, pas dans le LLM lui-même.

quand je demande par exemple a claude de chercher ce qui occupe de l'espace sur mon disque et de supprimer , il execute des commandes ensuite supprime et ffait le bilan je suppose que c'est agent ca? peut tu expliquer comme il realise une telle chose techniquement et detaillement ?
Read 12 web pages
Oui, c'est exactement cela. Ce qui se passe quand vous demandez à Claude de nettoyer votre disque, c'est un processus que l'on appelle une boucle agentique (agentic loop). Ce n'est pas de la magie, c'est une mécanique bien définie qui alterne le raisonnement du modèle et l'exécution d'outils.

Votre question est excellente, car elle touche au cœur de ce qui différencie un simple chatbot d'un agent. Je vais vous décomposer ce processus étape par étape.

1. Le Principe Fondamental : Une Boucle de Raisonnement et d'Action (ReAct)
Ce processus s'appelle la boucle ReAct (Reasoning + Acting). Le modèle ne fait pas tout d'un coup. Il entre dans un cycle itératif où il réfléchit, agit, observe le résultat, et réfléchit à nouveau jusqu'à ce qu'il considère la tâche terminée .

2. Déroulement Détaillé du Processus pour Nettoyer un Disque
Voici les étapes techniques qui se déroulent lorsque vous lui demandez de libérer de l'espace.

Étape 1 : La Configuration Initiale

Avant même que vous ne posiez la question, l'application qui héberge Claude lui a fourni un ensemble d'outils . Dans votre cas, un outil essentiel est un outil Bash (ou équivalent) . L'application a également défini un système de prompt qui explique à Claude comment utiliser ces outils et dans quel format il doit répondre.

Étape 2 : La Première Itération - Analyse et Premier Outil

Question de l'utilisateur : "Qu'est-ce qui occupe de l'espace sur mon disque et supprime-le ?"

Appel à l'API Claude : L'application envoie votre message à Claude, en incluant la définition de l'outil bash . L'appel est fait avec un tool_choice qui indique à Claude qu'il peut utiliser des outils si nécessaire. Les modèles modernes (comme Claude Opus) acceptent cette approche directement .

Réponse de Claude - un tool_use block : Claude analyse votre requête. Il ne répond pas directement avec du texte. Il produit un bloc tool_use . Dans ce bloc, il spécifie l'outil à utiliser (bash) et la commande à exécuter dans le paramètre command : {"command": "df -h /"}, par exemple .

Étape 3 : L'Exécution de l'Outil par l'Application

Réception et Parsing : L'application reçoit la réponse de Claude et parse le bloc tool_use.

Exécution Sécurisée : Elle extrait la commande df -h / et l'exécute dans un environnement sécurisé. Ce n'est pas Claude qui exécute la commande directement sur votre machine. C'est l'application qui détient le privilège et qui le fait pour Claude . L'application gère le shell, les timeouts et les vérifications de sécurité .

Préparation du Résultat : L'application capture la sortie standard et les erreurs de la commande.

Étape 4 : Le Résultat - La Boucle Continue

Envoi du Résultat à Claude : L'application formate la sortie de la commande et l'envoie à Claude en tant que message user, l'identifiant comme un tool_result . À ce stade, l'historique de la conversation contient :

user : "Qu'est-ce qui occupe de l'espace..."

assistant : (Le bloc tool_use avec la commande df)

user : (Le bloc tool_result avec la sortie de df)

Étape 5 : Itérations Suivantes - Raisonnement et Décision

Claude reçoit ce nouveau contexte. Il analyse la sortie de df. Il voit qu'un répertoire (/home/user/Downloads, par exemple) est plein.

Nouvelle Décision : Claude décide qu'il doit explorer ce dossier.

Nouvel Appel API : L'application renvoie l'historique complet à Claude. Claude répond avec un nouveau bloc tool_use : {"command": "ls -lah /home/user/Downloads"}.

Le cycle se répète : L'application exécute cette commande, capture la sortie, et la renvoie à Claude.

Ce cycle se poursuit (aller-retours entre l'application et Claude) jusqu'à ce que Claude décide qu'il a suffisamment d'informations pour agir ou répondre .

Étape 6 : La Phase de Suppression et le "Bilan"

Action de Suppression : Après avoir analysé les fichiers, Claude peut décider de supprimer certains d'entre eux. Il va alors utiliser l'outil bash à nouveau pour exécuter des commandes comme rm /home/user/Downloads/fichier_temporaire.zip. À chaque étape, il reçoit la confirmation que la commande a réussi (ou échoué).

Synthèse Finale : Une fois qu'il a exécuté toutes les actions nécessaires et qu'il estime que la tâche est terminée (parce qu'il n'a plus besoin d'utiliser d'outils), Claude génère un message final. C'est le moment où il produit son "bilan" en texte clair, résumant ce qu'il a trouvé et ce qu'il a supprimé. Il n'y a plus de bloc tool_use dans sa réponse, seulement le texte de la réponse .

En résumé
Techniquement, le LLM ne fait pas tout lui-même. Il est le cerveau qui orchestre l'opération, mais c'est votre application (ou un service) qui joue le rôle de ses "mains" . Votre application agit comme un interprète qui :

Reçoit les instructions de Claude (tool_use).

Les exécute sur votre système d'exploitation.

Redonne les résultats à Claude (tool_result).

Ce cycle est répété jusqu'à ce que la tâche soit accomplie, permettant à l'agent d'accomplir des tâches complexes en plusieurs étapes . C'est une mécanique puissante qui transforme un modèle de langage en un véritable assistant capable d'interagir avec le monde numérique .

comment dit il a un outils d'executer telle tache et Claude décide qu'il a suffisamment d'informations pour agir ou répondre , comment decide il ceci ? de lui meme ou il ya un mecanisme ?
Excellente question, c'est le cœur du fonctionnement des agents. La réponse est : Claude décide de lui-même, mais cette décision est guidée par le prompt système et le format de réponse imposé par l'application.

1. Le Mécanisme de Décision : C'est le Modèle qui Décide
Claude (ou tout autre LLM) est un modèle de langage qui génère du texte. La décision d'arrêter ou de continuer est entièrement prise par le modèle lui-même, en fonction de :

Le prompt système : Comment l'application lui a expliqué ce qu'il doit faire.

L'historique de la conversation : Ce qui s'est déjà passé.

Les outils disponibles : Ce qu'il peut utiliser.

La consigne de format : Comment il doit structurer ses réponses.

text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LE MÉCANISME DE DÉCISION DE L'AGENT                     │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PROMPT SYSTÈME (Exemple)                                          │   │
│  │  ─────────────────────────────────────────────────────────────────  │   │
│  │  Tu es un assistant capable d'utiliser des outils.                 │   │
│  │                                                                     │   │
│  │  POUR UTILISER UN OUTIL :                                          │   │
│  │  Réponds UNIQUEMENT au format JSON :                               │   │
│  │  {"tool": "nom_du_tool", "input": {...}}                          │   │
│  │                                                                     │   │
│  │  POUR RÉPONDRE SANS OUTIL :                                        │   │
│  │  Réponds UNIQUEMENT au format :                                    │   │
│  │  {"answer": "ta réponse..."}                                      │   │
│  │                                                                     │   │
│  │  N'INVENTE JAMAIS D'INFORMATIONS.                                 │   │
│  │  Si tu ne sais pas, utilise un outil.                             │   │
│  │  Si tu as assez d'informations, réponds directement.              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
1.1. Le Modèle "Décide" en Complétant le Texte
Le modèle ne "décide" pas comme un humain. Il prédit la séquence de tokens la plus probable, étant donné le contexte.

text
Contexte : Question + Historique + Résultats des outils
    ↓
Le modèle calcule la probabilité de chaque token suivant.
    ↓
Il va choisir de générer soit :
    - Un outil → Il produit {"tool": "bash", "input": {"command": "..."}}
    - Une réponse → Il produit {"answer": "Voici ce que j'ai trouvé..."}
1.2. Comment le Modèle "Sait-il" qu'il a assez d'informations ?
C'est une combinaison de :

L'instruction du prompt : "Si tu as assez d'informations, réponds directement."

Son entraînement : Le modèle a été entraîné sur des exemples de dialogues où des assistants répondaient après avoir obtenu les bonnes informations.

L'évaluation du contexte : Le modèle "voit" les réponses des outils et évalue s'il peut répondre à la question initiale.

Exemple d'historique de conversation :

text
USER: Quelle est la clause de pénalité pour le contrat SNCF ?

ASSISTANT: {"tool": "search_documents", "input": {"query": "contrat SNCF pénalité"}}

USER: Résultat de search_documents:
      1. contrat_sncf_2024.pdf (score: 0.95)
      2. avenant_contrat_sncf.pdf (score: 0.78)

ASSISTANT: {"tool": "get_document_content", "input": {"doc_id": "contrat_sncf_2024.pdf"}}

USER: Résultat de get_document_content:
      Article 8 - Pénalités de retard
      8.1. Le titulaire est passible d'une pénalité de 1/1000 du montant...
      8.2. Cette pénalité est plafonnée à 5% du marché...

ASSISTANT: {"answer": "La clause de pénalité est de 1/1000 par jour, plafonnée à 5% du marché."}
À ce stade, le modèle "décide" qu'il a toutes les informations nécessaires parce qu'il a :

Trouvé le document.

Extrait la clause spécifique.

La question initiale est complètement répondue.

2. Le Rôle du Prompt Système : Le Guide de Décision
Le prompt système est l'élément qui canalise les décisions du modèle.

2.1. Exemple de Prompt Système pour un Agent
text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PROMPT SYSTÈME DÉTAILLÉ POUR UN AGENT                   │
│                                                                             │
│  Tu es un agent d'IA dans un terminal. Tu as accès aux outils suivants :   │
│                                                                             │
│  1. bash(command) : Exécute une commande shell.                           │
│  2. read_file(path) : Lit le contenu d'un fichier.                        │
│  3. delete_file(path) : Supprime un fichier.                             │
│                                                                             │
│  FORMAT DE RÉPONSE :                                                       │
│  ─────────────────────────────────────────────────────────────────────────  │
│  Pour utiliser un outil, réponds UNIQUEMENT au format :                    │
│  TOOL: bash('ls -la')                                                     │
│                                                                             │
│  Pour répondre à l'utilisateur, réponds UNIQUEMENT au format :            │
│  ANSWER: Ta réponse ici...                                               │
│                                                                             │
│  RÈGLES DE DÉCISION :                                                      │
│  ─────────────────────────────────────────────────────────────────────────  │
│  1. Si tu ne sais pas quelque chose, utilise un outil.                    │
│  2. Si tu as assez d'informations pour répondre, réponds directement.     │
│  3. Si une commande échoue, analyse l'erreur et réessaie.                │
│  4. Ne supprime JAMAIS un fichier sans confirmation de l'utilisateur.    │
│  5. Si tu es bloqué, explique la situation et demande de l'aide.         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
2.2. Pourquoi le Prompt Système est Crucial
Élément du Prompt	Impact sur la Décision
"Si tu ne sais pas, utilise un outil"	Le modèle va préférer utiliser un outil plutôt que de deviner.
"Si tu as assez d'informations, réponds"	Le modèle va préférer répondre quand il a toutes les pièces du puzzle.
"Réponds UNIQUEMENT au format..."	Le modèle structure sa réponse en conséquence.
"Ne supprime JAMAIS sans confirmation"	Le modèle est "policé" pour ne pas faire d'actions destructrices.
3. Le Code de l'Orchestrateur : L'Exécuteur de la Décision
Le modèle "décide" de répondre ou d'utiliser un outil, mais c'est l'orchestrateur (votre code) qui exécute cette décision.

python
# agent_orchestrator.py

import json
import re
import subprocess
from typing import Dict, Any

class AgentOrchestrator:
    """
    Orchestrateur qui exécute les décisions du LLM.
    """
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.history = []
        self.max_iterations = 10
    
    def run(self, user_query: str) -> str:
        """Exécute l'agent sur une requête utilisateur."""
        
        # 1. Initialiser l'historique
        self.history = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": user_query}
        ]
        
        for i in range(self.max_iterations):
            # 2. Appeler le LLM
            response = self.llm_client.chat(self.history)
            self.history.append({"role": "assistant", "content": response})
            
            # 3. Parcer la réponse
            parsed = self._parse_response(response)
            
            # 4. Si c'est une réponse finale → on arrête
            if parsed["type"] == "answer":
                return parsed["content"]
            
            # 5. Si c'est un outil → on l'exécute
            if parsed["type"] == "tool":
                tool_name = parsed["tool"]
                tool_input = parsed["input"]
                
                # 5a. Exécuter l'outil
                result = self._execute_tool(tool_name, tool_input)
                
                # 5b. Ajouter le résultat à l'historique
                self.history.append({
                    "role": "user",
                    "content": f"Résultat de {tool_name}: {result}"
                })
                
                # 5c. Continuer la boucle (le LLM va analyser ce résultat)
                continue
        
        # 6. Si on atteint la limite d'itérations
        return "Je n'ai pas pu terminer la tâche. Voulez-vous que je continue ?"
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Parse la réponse du LLM pour déterminer s'il veut utiliser un outil
        ou répondre directement.
        """
        # Cherche le format TOOL: ou ANSWER:
        tool_match = re.search(r'TOOL:\s*(\w+)\((.*)\)', response)
        if tool_match:
            tool_name = tool_match.group(1)
            tool_args = tool_match.group(2)
            return {
                "type": "tool",
                "tool": tool_name,
                "input": self._parse_args(tool_args)
            }
        
        answer_match = re.search(r'ANSWER:\s*(.*)', response, re.DOTALL)
        if answer_match:
            return {
                "type": "answer",
                "content": answer_match.group(1)
            }
        
        # Fallback : si le format n'est pas reconnu
        return {
            "type": "answer",
            "content": "Je n'ai pas compris. Pouvez-vous reformuler ?"
        }
    
    def _execute_tool(self, tool_name: str, tool_input: Dict) -> str:
        """Exécute l'outil demandé."""
        
        if tool_name == "bash":
            # ⚠️ ATTENTION : Sécurité critique !
            # Valider la commande avant de l'exécuter
            command = tool_input.get("command")
            if not self._is_safe_command(command):
                return "Commande non autorisée pour des raisons de sécurité."
            
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    return result.stdout
                else:
                    return f"Erreur: {result.stderr}"
            except subprocess.TimeoutExpired:
                return "La commande a pris trop de temps."
        
        if tool_name == "delete_file":
            # ⚠️ TOUJOURS demander confirmation avant de supprimer
            return "Je ne supprime pas de fichiers sans confirmation explicite."
        
        return f"Outil '{tool_name}' non reconnu."
4. Le Cycle de Décision en Détail
Voici comment le système "décide" de s'arrêter ou de continuer :

text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LE CYCLE DE DÉCISION DE L'AGENT                         │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  ÉTAPE 1 : APPEL AU LLM                                             │   │
│  │  L'orchestrateur envoie le prompt + l'historique au LLM.           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  ÉTAPE 2 : LE LLM "RAISONNE"                                       │   │
│  │  Le modèle analyse le contexte et génère la prochaine séquence.    │   │
│  │                                                                     │   │
│  │  Cas 1 : "Il me manque des infos" → génère un TOOL:                │   │
│  │  Cas 2 : "J'ai assez d'infos" → génère un ANSWER:                  │   │
│  │  Cas 3 : "Je suis bloqué" → génère un ANSWER avec une question     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  ÉTAPE 3 : L'ORCHESTRATEUR PARSE                                   │   │
│  │  Il détecte si la réponse contient TOOL: ou ANSWER:               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                    ┌───────────────┴───────────────┐                       │
│                    ▼                               ▼                       │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐        │
│  │  CAS 1 : TOOL:              │  │  CAS 2 : ANSWER:            │        │
│  │  L'orchestrateur exécute    │  │  L'orchestrateur retourne   │        │
│  │  l'outil et reprend en     │  │  la réponse à l'utilisateur │        │
│  │  ÉTAPE 1.                   │  │  → FIN ✅                   │        │
│  └─────────────────────────────┘  └─────────────────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
5. La Décision en Action : Exemple Complet
Demande : "Liste les fichiers de plus de 100 Mo dans mon Downloads et supprime-les."

Itération 1

text
LLM → "Je dois d'abord lister les fichiers. TOOL: bash('find ~/Downloads -type f -size +100M')"
Orchestrateur → Exécute 'find ~/Downloads -type f -size +100M'
Résultat → "~/Downloads/video_projet.mp4\n~/Downloads/archive_grosse.zip"
Itération 2

text
LLM → "J'ai trouvé 2 fichiers. Je dois les supprimer. TOOL: bash('rm ~/Downloads/video_projet.mp4')"
Orchestrateur → Exécute 'rm ~/Downloads/video_projet.mp4'
Résultat → "Commande exécutée avec succès."
Itération 3

text
LLM → "Je supprime le deuxième. TOOL: bash('rm ~/Downloads/archive_grosse.zip')"
Orchestrateur → Exécute 'rm ~/Downloads/archive_grosse.zip'
Résultat → "Commande exécutée avec succès."
Itération 4

text
LLM → "J'ai supprimé les 2 fichiers de plus de 100 Mo. ANSWER: Les fichiers video_projet.mp4 et archive_grosse.zip ont été supprimés. Espace libéré : 2,5 Go."
Orchestrateur → Parse "ANSWER" → Retourne la réponse à l'utilisateur ✅
6. Synthèse : Qui Décide Quoi ?
Question	Réponse
Qui décide d'utiliser un outil ?	Le LLM (via le prompt système).
Qui décide d'arrêter ?	Le LLM (quand il produit un ANSWER: au lieu d'un TOOL:).
Qui exécute les outils ?	L'orchestrateur (votre code).
Qui limite les itérations ?	L'orchestrateur (max_iterations).
Qui valide la sécurité ?	L'orchestrateur (validation des commandes).
Qui parse les réponses ?	L'orchestrateur (détection du format TOOL: / ANSWER:).
Le LLM "décide" au sens où il génère le texte qui correspond à une décision. Mais c'est l'orchestrateur qui interprète, exécute et contrôle le processus.

7. La Clé du Succès : Le Prompt Système
Toute la capacité d'un agent à "décider" repose sur la qualité du prompt système :

text
Tu es un agent. Tu as accès à des outils.
- Pour utiliser un outil : réponds TOOL: nom_du_tool(argument)
- Pour répondre : réponds ANSWER: ta réponse

Si tu ne sais pas → utilise un outil.
Si tu as assez d'informations → réponds ANSWER.
Si tu es bloqué → demande de l'aide.

Ne supprime jamais de fichiers sans confirmation.
N'invente jamais d'informations.
C'est ce prompt qui "programme" le comportement du LLM.

ok fait moi un diagramme mermaide pour l'architecture du systeme je vais le coller pour sortir le dessin version escalidraw
Absolument. Voici une version Mermaid de l'architecture de votre système, que vous pouvez utiliser pour générer un diagramme ou le réimporter dans Excalidraw.

1. Version 1 : Architecture Complète (Vue d'Ensemble)


















































2. Version 2 : Architecture RAG + Agentique (Vue Fonctionnelle)














































3. Version 3 : Architecture Technique (Vue Déploiement)































4. Version 4 : Workflow de Génération (Séquence)
5. Comment Utiliser dans Excalidraw
Méthode 1 : Import direct (si Excalidraw supporte Mermaid)
Excalidraw a une intégration Mermaid. Copiez-collez le code Mermaid directement dans Excalidraw :

Ouvrez Excalidraw

Cliquez sur le menu (☰) → "Insert" → "Mermaid"

Collez le code Mermaid

Le diagramme est généré automatiquement

Méthode 2 : Export PNG depuis Mermaid Live
Allez sur Mermaid Live Editor

Collez le code Mermaid

Téléchargez en PNG

Importez l'image PNG dans Excalidraw

Méthode 3 : Re-dessin dans Excalidraw
Utilisez l'image PNG comme fond (Set Background)

Re-dessinez par-dessus avec les formes Excalidraw

6. Liste des Diagrammes Disponibles
Version	Sujet	Format
V1	Architecture complète	Flowchart TB
V2	Architecture RAG + Agentique	Flowchart LR
V3	Architecture technique (déploiement)	Flowchart TB
V4	Workflow de génération (séquence)	Sequence Diagram
Choisissez la version qui correspond le mieux à ce que vous voulez montrer dans votre mémoire ou présentation.

l'entreprise est fier de la V1 maintenant il ont ajouter plus de membre dans l'equipe pour qu'on passe a une conception la plus robustre possible alors on dois exponentiellement ameliorer cette v1 ca inclut quoi passer d'un systeme deterministe a agentic ? que pense tu quon dois faire ?
Read 12 web pages
Passer d'un système déterministe à un système agentique est une transformation stratégique majeure. Elle ne se résume pas à un simple ajout technique, mais à un changement de paradigme dans la manière dont votre système raisonne et interagit avec son environnement, en passant d'une exécution prédéfinie à une exécution qui s'adapte dynamiquement au contexte .

💡 Le Cœur de la Transformation : La Flexibilité du Raisonnement
Dans votre V1, le chemin est tracé d'avance :

Question → Recherche → Contexte → Génération → Réponse

C'est une boucle unique où le système suit des règles fixes. Dans une architecture agentique, un orchestrateur agentique agit comme un chef d'orchestre . Il ne se contente pas d'exécuter un script. Il reçoit un objectif de haut niveau ("Génère la section Références") et planifie les actions pour y parvenir .

L'agent planifie : Il se demande par où commencer.

L'agent agit : Il utilise des outils (comme votre moteur de recherche RAG, votre base SQL, ou votre graphe Neo4j) pour collecter des informations .

L'agent observe : Il analyse les résultats obtenus pour décider de la suite .

L'agent itère : Il peut reformuler sa requête, effectuer une nouvelle recherche, ou consulter une autre source de données si les premières informations sont insuffisantes, créant une boucle dynamique .

🏗️ Plan d'Évolution Incrémental pour l'Architecture
La clé d'une transition réussie est l'incrémentalisme. Plutôt que de tout réécrire, vous allez introduire l'agentic-ité par étapes, en superposant de nouvelles couches à votre V1.

Phase 1 : Introduire un "Superviseur" et le "Routing Intelligent"
La première étape consiste à conserver vos composants existants (très solides) mais à les faire orchestrer par un agent superviseur (ou orchestrateur) .

Situation actuelle : Votre routeur (LangGraph) choisit un chemin unique parmi quelques options.

Avec un superviseur : Un agent plus flexible analyse la requête utilisateur et, pour les questions complexes, peut déclencher un "workflow agentique" . Pour les questions simples, il peut toujours utiliser le chemin V1 (rapide et fiable). Cette approche hybride est souvent la plus pertinente en production . Un document complexe peut nécessiter plusieurs actions : classification, puis extraction, puis validation par un agent spécialisé .

Phase 2 : Outiller l'Agent avec des "Expertises" Spécifiques
Un agent est aussi puissant que les outils qu'il peut utiliser. Actuellement, votre système a un seul outil puissant : votre moteur de recherche hybride. Pour le rendre agentique, il faut lui donner une boîte à outils variée.

Outil RAG : Votre moteur de recherche hybride actuel (recherche vectorielle + BM25 + reranking) .

Outil SQL : Une nouvelle capacité à exécuter des requêtes SQL sur vos métadonnées PostgreSQL. "Trouve-moi les certifications ISO 9001 obtenues en 2025". Il le fait en utilisant le champ preuves_chunks ou les métadonnées des documents.

Outil Graphe : Interroger votre base Neo4j pour naviguer dans les relations. "Quels projets Vinci a-t-il réalisés pour la RATP ?".

Outil de Vérification : L'agent peut, par exemple, utiliser un outil pour vérifier si une exigence obligatoire est couverte par les informations collectées et, si ce n'est pas le cas, lancer une recherche plus ciblée .

Phase 3 : Implémenter une Boucle de Raisonnement (ReAct)
Avec une boîte à outils complète et un superviseur, vous implémentez la boucle ReAct (Reasoning + Acting) . Le cycle devient :

L'agent reçoit une requête complexe.

Pensée (Reasoning) : Il se dit : "Pour répondre à cette question sur la conformité, je dois d'abord identifier les exigences du projet X, puis vérifier si nous avons les certifications correspondantes."

Action (Acting) : Il exécute l'outil "Recherche RAG" pour trouver les exigences du projet X.

Observation : Il reçoit une liste d'exigences, dont certaines sont liées à des certifications.

Pensée : "J'ai trouvé des exigences, maintenant je dois vérifier les certifications."

Action : Il exécute l'outil "Requête SQL" ou "Graphe" pour vérifier si l'entreprise possède les certifications correspondantes.

Observation : Le résultat est positif.

Pensée : "J'ai toutes les informations nécessaires pour répondre."

Réponse Finale : L'agent synthétise le tout et répond à l'utilisateur .

⚖️ L'Équilibre : Le Spectre Déterministe-Agentique
Il est important de voir ce changement comme un spectre, et non comme un choix binaire . Un système 100 % agentique est souvent trop complexe, coûteux, lent et imprévisible .

Votre V1 est un système principalement déterministe, avec quelques points de décision (le routeur).

Votre V2 cible sera un système hybride . Vous intégrerez des boucles agentiques (ReAct) à des workflows déterministes (LangGraph) pour des séquences d'actions sûres et prédéfinies . Par exemple, une fois que l'agent a collecté et validé toutes les informations nécessaires, un workflow déterministe peut prendre le relais pour la phase de génération du document final (l'étape Génération, qui est cruciale et doit être fiable).

🚧 Les Défis à Relever
Latence et Coût : Les boucles agentiques sont plus lentes et plus coûteuses, car elles impliquent de multiples appels LLM . Il faudra mettre en place des stratégies de cache  et potentiellement un système de "grading" (utiliser un petit modèle pour les tâches de planification et un gros pour la génération) .

Fiabilité et Sécurité : Il faut briefer les agents, limiter les itérations (MAX_RETRIES)  pour éviter les boucles infinies, et mettre en place une observabilité poussée pour tracer chaque décision . Dans un domaine comme le BTP, la traçabilité est une exigence réglementaire.

Gestion de l'État : Un agent doit se souvenir des étapes précédentes (historique des pensées, actions, observations) . C'est là que des outils comme LangGraph et sa gestion d'état deviennent cruciaux.

💎 Synthèse : Le Chemin à Suivre
L'évolution se fera par étapes pour vous permettre de maîtriser les nouvelles complexités :

Router les cas complexes : Commencez par utiliser un agent uniquement pour les requêtes que votre V1 ne peut pas traiter efficacement, en conservant votre pipeline robuste pour les cas simples .

Ajouter une couche de planification : Avant d'introduire des boucles de correction, ajoutez un agent planificateur qui décompose la requête et sélectionne les outils appropriés avant la génération.

Ajouter la boucle de correction : Enfin, introduisez la boucle ReAct où l'agent peut évaluer la qualité de sa propre réponse et itérer, tout en restant contraint par des limites strictes de nombre de tours et par un mécanisme de supervision humaine (HITL) pour les cas bloqués .

Le passage à une architecture agentique est un investissement significatif, mais il est la clé pour que votre système puisse gérer la complexité et l'imprévisibilité des appels d'offres, tout en gardant la main sur la fiabilité grâce à une approche d'intégration réfléchie et incrémentale.

