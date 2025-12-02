from typing import TypedDict, List, Any
from app.rag.qa_graph import build_qa_graph
from langgraph.graph import StateGraph, START, END

class RouterState(TypedDict, total=False):
    question: str
    text: str
    user_role: str
    mode: str               # 模式标记，如qa rag kb...
    answer: str
    docs: List[Any]

def decide_route(state: RouterState) -> str:
    mode = (state.get("mode") or "").lower().strip()
    if mode in {"qa", "rag", "kb"}:
        return "qa"
    return "qa"

def route_node(state: RouterState) -> dict:
    return {}

def build_router_graph():
    """
    构建顶级路由
    :return:
    """
    qa_graph = build_qa_graph()

    g = StateGraph(RouterState)

    g.add_node("route", route_node)
    g.add_node("qa", qa_graph)

    g.add_edge(START, "route")

    g.add_conditional_edges(
        "route",
        decide_route,
        {"qa":"qa"}
    )

    g.add_edge("qa", END)

    return g.compile()

router_graph = build_router_graph()