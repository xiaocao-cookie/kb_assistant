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
    missing_fields: List[str]
    violations: List[str]

    leave_id: str

def decide_route(state: RouterState) -> str:
    mode = (state.get("mode") or "").lower().strip()

    # 关键词路由
    text = (state.get("text") or state.get("question") or "").lower()
    qa_keywords = [
        "还能", "还可以", "其他问题", "帮我查", "我想问", "请问", "可以告诉我", "想咨询"
    ]

    leave_keywords = [
        "请假", "年假", "病假", "事假", "休假", "调休", "假期", "请一天年假", "请半天假", "请一天假", "审批通过"
    ]

    approve_keywords = [
        "审批通过",
        "批准",
        "同意",
        "同意请假",
        "批准请假",
        "通过请假",
        "审批同意",
        "已批准",
        "通过审批",
        "批了",
        "同意了",
    ]

    reject_keywords = [
        "驳回",
        "拒绝",
        "不批准",
        "不同意",
        "审批拒绝",
        "拒批",
        "打回",
        "否决",
        "拒绝请假",
        "驳回请假",
    ]

    # 转 qa
    if any(k in text for k in qa_keywords):
        return "qa"

    # 转 leave
    if any(k in text for k in leave_keywords):
        return "leave"

    if any(k in text for k in approve_keywords):
        return "leave"

    if any(k in text for k in reject_keywords):
        return "leave"


    active = (state.get("active_route") or "").lower().strip()
    if active == "leave" and mode not in {"qa", "rag", "kb"}:
        return "leave"

    if mode in {"qa", "rag", "kb"}:
        return "qa"
    if mode in {"leave", "hr"}:
        return "leave"

    return "qa"

def route_node(state: RouterState) -> dict:
    print(f"------------------------{decide_route(state)}------------------------")
    active = decide_route(state)
    return {"active_route": active}

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