from __future__ import annotations

import json
import uuid
import re

from datetime import datetime
from typing import Any, Dict

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage

from app.deps import get_llm
from app.workflows.leave.models import LeaveState
from app.workflows.leave.rules import validate_leave
from app.prompts.leave_prompt import SLOT_SYSTEM, SLOT_USER
from app.prompts.parse_date_prompt import TIME_USER, TIME_SYSTEM
from app.db_ops.leave_sql import get_leave_balance, get_leave_request, cancel_leave_request, insert_leave_request

def _safe_json_load(s: str) -> Dict[str , Any]:
    """
    将大模型返回的 json 转换为字典
    :param s: json 字符串
    :return: 字典
    """
    if not s:
        return {}
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:].strip()
    try:
        return json.loads(s)            # 将 json 字符串转换为字典
    except Exception:
        return {}


def _safe_iso(s: Any) -> str | None:
    """
    将ISO格式的时间转为datetime对象
    :param s: 时间
    :return: datetime对象 或 None
    """
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    try:
        datetime.fromisoformat(s)
        return s
    except Exception:
        print(f"e: {Exception.__name__}")

def _extract_leave_id(text: str) -> str:
    """
    从 text 中匹配 Leave_id(LV-...)
    """
    if not text:
        return None
    m = re.search(r"\bLV-[0-9a-fA-F]{6,12}\b", text)
    return m.group(0) if m else None


def extract_slots_node(state: LeaveState) -> dict:
    """
    抽取槽位
    :param state:
    :return:
    """
    llm = get_llm()
    text = state.get("text", "") or state.get("question", "") or ""

    messages = [
        SystemMessage(content=SLOT_SYSTEM),
        HumanMessage(content=SLOT_USER.format(text=text)),
    ]
    raw = llm.invoke(messages).content
    data = _safe_json_load(raw)

    req = state.get("req") or {}
    req.update({
        "leave_type": data.get("leave_type") or req.get("leave_type"),
        "start_time": _safe_iso(data.get("start_time")) or req.get("start_time"),
        "end_time": _safe_iso(data.get("end_time")) or req.get("end_time"),
        "reason": data.get("reason") or req.get("reason"),
    })
    req["requester"] = state.get("requester", "anonymous")
    return {"req": req}


def validate_node(state: LeaveState) -> dict:
    """
    请假的规则校验
    """
    req = state.get("req") or {}
    requester = req.get("requester") or state.get("requester", "anonymous")

    bal = get_leave_balance(requester) or {}  # 看看数据库里还有几天假期可以用
    annual_balance = float(bal.get("annual_days", 0))

    missing, violations = validate_leave(req, balance_days=annual_balance)
    return {"missing_fields": missing, "violations": violations, "req": req}


def decide_next(state: LeaveState) -> str:
    """
    决定走信息补充还是确认请假信息
    """
    if state.get("missing_fields") or state.get("violations"):
        return "need_info"
    return "confirm"


def need_info_node(state: LeaveState) -> dict:
    """
    补充信息的提示
    """
    missing = state.get("missing_fields") or []
    violations = state.get("violations") or []

    tips = []
    if missing:
        tips.append("缺少信息：" + "、".join(missing))
    if violations:
        tips.append("规则问题：" + "；".join(violations))

    return {"answer": "；".join(tips) + "。请补充/修正后再说一次。"}


def confirm_node(state: LeaveState) -> dict:
    """
    请假信息确认
    """
    req = state.get("req") or {}
    ans = (
        "请确认你的请假信息：\n"
        f"- 类型：{req.get('leave_type')}\n"
        f"- 开始：{req.get('start_time')}\n"
        f"- 结束：{req.get('end_time')}\n"
        f"- 时长：{req.get('duration_days')} 天\n"
        f"- 原因：{req.get('reason') or '无'}\n"
        "回复“确认”提交，或直接回复修改后的信息。"
    )
    return {"answer": ans}


def decide_confirm(state: LeaveState) -> str:
    """
    是否确认请假
    """
    text = (state.get("text") or "").strip().lower()
    if text in {"确认", "确定", "yes", "ok", "submit"}:
        return "create"
    return "end"


def create_leave_node(state: LeaveState) -> dict:
    """
    生成请假单（这里是虚拟的请假单，并没有连接数据库）
    :param state:
    :return:
    """
    req = state.get("req") or {}
    leave_id = "LV-" + uuid.uuid4().hex[:8]
    req_to_save = {
        "leave_id": leave_id,
        "requester": req["requester"],
        "leave_type": req["leave_type"],
        "start_time": req["start_time"],
        "end_time": req["end_time"],
        "duration_days": req["duration_days"],
        "reason": req.get("reason"),
    }
    insert_leave_request(req_to_save)
    return {"leave_id": leave_id, "answer": f"已为你提交请假申请，编号 {leave_id}，等待审批。"}


def intent_node(state: LeaveState) -> dict:
    return {}


def query_leave_node(state: LeaveState) -> dict:
    """
    请假单查询
    """
    text = state.get("text") or state.get("question") or ""
    leave_id = state.get("leave_id") or _extract_leave_id(text)

    if not leave_id:
        return {"answer": "请提供请假单编号，我才能帮你查询"}

    row = get_leave_request(leave_id)
    if not row:
        return {"answer": f"未找到编号为 {leave_id} 的请假申请"}

    return {
        "leave_id": leave_id,
        "answer": (
            f"请假单 {leave_id} 当前状态：{row['status']}\n"
            f"类型：{row['leave_type']}\n"
            f"开始：{row['start_time']}\n"
            f"结束：{row['end_time']}\n"
            f"时长：{row['duration_days']} 天\n"
            f"原因：{row.get('reason') or '无'}"
        ),
    }


def cancel_leave_node(state: LeaveState) -> dict:
    """
    请假单取消
    :param state:
    :return:
    """
    text = state.get("text") or state.get("question") or ""
    leave_id = state.get("leave_id") or _extract_leave_id(text)

    if not leave_id:
        return {"answer": "请提供要取消的请假单编号。"}

    ok = cancel_leave_request(leave_id)
    if not ok:
        return {"answer": "取消失败：未找到，或单据不是待审批状态（PENDING）。"}

    return {"leave_id": leave_id, "answer": f"已取消请假申请 {leave_id}。"}


def parse_time_node(state: LeaveState) -> dict:
    """
    从文本中解析时间
    """
    req = state.get("req") or {}
    if _safe_iso(req.get("start_time")) and _safe_iso(req.get("end_time")):
        return {}

    llm = get_llm()
    text = state.get("text") or state.get("question") or ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    messages = [
        SystemMessage(content=TIME_SYSTEM),
        HumanMessage(content=TIME_USER.format(now=now, text=text))
    ]
    raw = llm.invoke(messages).content
    data = _safe_json_load(raw)

    start = _safe_iso(data.get("start_time"))
    end = _safe_iso(data.get("end_time"))

    if start or end:
        req.update({
            "start_time": start or req.get("start_time"),
            "end_time": end or req.get("end_time"),
        })
        return {"req": req}
    return {}


def decide_intent(state: LeaveState) -> str:
    """
    路由分发，查询请假单/解析时间/取消请假单
    """
    text = (state.get("text") or state.get("question") or "").lower()

    if any(k in text for k in ["取消", "撤销", "作废"]):
        return "cancel"

    if any(k in text for k in ["查询", "查", "状态", "进度", "结果"]):
        if any(k in text for k in ["请假", "年假", "病假", "事假", "休假", "调休", "假期", "申请", "单"]):
            return "query"

    return "apply"


def build_leave_graph():
    """
    构建请假图
    :return: 已编译的图对象
    """
    g = StateGraph(LeaveState)

    g.add_node("intent", intent_node)
    g.add_node("cancel", cancel_leave_node)
    g.add_node("parse_time", parse_time_node)
    g.add_node("query", query_leave_node)

    g.add_node("extract", extract_slots_node)
    g.add_node("validate", validate_node)
    g.add_node("need_info", need_info_node)
    g.add_node("confirm", confirm_node)
    g.add_node("create", create_leave_node)

    g.add_edge(START, "intent")
    g.add_conditional_edges(
        "intent",
        decide_intent,
        {
            "apply": "parse_time",
            "query": "query",
            "cancel": "cancel"
        }
    )

    g.add_edge("parse_time", "extract")
    g.add_edge("extract", "validate")

    g.add_conditional_edges(
        "validate",
        decide_next,
        {
            "need_info": "need_info",
            "confirm": "confirm"
        }
    )

    g.add_conditional_edges(
        "confirm",
        decide_confirm,
        {
            "create": "create",
            "end": END
        }
    )

    g.add_edge("query", END)
    g.add_edge("cancel", END)
    g.add_edge("need_info", END)
    g.add_edge("create", END)

    return g.compile()