"""Graphe LangGraph V1 — nœuds déterministes, pas d'agents autonomes."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.workflow.nodes import chitchat, export_flag, generate, retrieve, route


class WorkflowState(TypedDict, total=False):
    messages: list
    history: list
    tenant_id: str
    intent: str
    query: str
    retrieved: list
    answer: str
    citations: list
    section_key: str
    section_title: str
    generate_all: bool
    export_requested: bool


def _dispatch(state: WorkflowState) -> str:
    intent = state.get("intent") or "hybrid_rag"
    if intent == "export":
        return "export_doc"
    if intent == "smalltalk":
        return "chitchat"
    return "retrieve"


def build_graph():
    graph = StateGraph(WorkflowState)
    graph.add_node("route", route.route)
    graph.add_node("retrieve", retrieve.retrieve)
    graph.add_node("generate", generate.generate)
    graph.add_node("chitchat", chitchat.chitchat)
    graph.add_node("export_doc", export_flag.export_doc)
    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        _dispatch,
        {
            "export_doc": "export_doc",
            "chitchat": "chitchat",
            "retrieve": "retrieve",
        },
    )
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    graph.add_edge("chitchat", END)
    graph.add_edge("export_doc", END)
    return graph.compile()


_COMPILED = None


def compiled_graph():
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = build_graph()
    return _COMPILED
