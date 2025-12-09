from __future__ import annotations
from typing import TypedDict, List, Any
from app.rag.qa_graph import build_qa_graph
from langgraph.graph import StateGraph, START, END
from app.workflows.leave.leave_graph import build_leave_graph

class RouterState(TypedDict, total=False):
    question: str
    text: str
    user_role: str
    mode: str               # 模式标记，如qa rag kb leave...
    answer: str
    active_route: str

    # QA_Graph 所需信息
    docs: List[Any]

    # Leave_Graph 所需信息
    requester: str
    req: dict
    missing_fields: list[str]
    violations: list[str]

    docs: list[Any]
    leave_id: str

def decide_route(state: RouterState) -> str:
    mode = (state.get("mode") or "").lower().strip()

    active = (state.get("active_route") or "").lower().strip()
    if active == "leave" and mode not in {"qa", "rag", "kb"}:
        return "leave"

    if mode in {"qa", "rag", "kb"}:
        return "qa"
    if mode in {"leave", "hr"}:
        return "leave"

    # todo: 关键词路由的解释
    text = (state.get("text") or state.get("question") or "").lower()
    if any(k in text for k in ["请假", "年假", "病假", "事假", "休假", "调休", "假期", "请一天假", "请半天假"]):
        return "leave"

    return "qa"

def route_node(state: RouterState) -> dict:
    return {"active_route": decide_route(state)}

def build_router_graph():
    """
    构建顶级路由
    :return:
    """
    qa_graph = build_qa_graph()
    leave_graph = build_leave_graph()

    g = StateGraph(RouterState)

    g.add_node("route", route_node)
    g.add_node("qa", qa_graph)
    g.add_node("leave", leave_graph)

    g.add_edge(START, "route")

    g.add_conditional_edges(
        "route",
        decide_route,
        {"qa":"qa", "leave": "leave"}
    )

    g.add_edge("qa", END)
    g.add_edge("leave", END)

    return g.compile()

router_graph = build_router_graph()